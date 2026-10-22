// -----------------------------------------------------------------------------
// enhance_body.inc - the per-pixel pipeline, shared by both kernel variants.
//
// Included *inside* the pipelined loop of each top-level function on purpose: the line
// buffers and window registers are function-local statics carrying HLS ARRAY_PARTITION
// pragmas, and those cannot be attached to a struct member, so a real function call would
// change the storage and the schedule. Textual inclusion keeps the hardware identical and
// only the origin of the configuration differs between the two variants.
//
// Expects in scope:  s_in, s_out, the line-buffer statics, col, phase, and the nine
//                    configuration values (clarity, knee, gain_lo, gain_hi, thresh,
//                    binarize, invert, mono, split_x).
// -----------------------------------------------------------------------------

        enh_pixel_t pin = s_in.read();
        enh_pixel_t pout = pin;   // carries keep/strb/user/last/id/dest through

        ap_uint<24> rgb_in = pin.data.range(23, 0);
        ap_uint<8> r_in = rgb_in.range(23, 16);
        ap_uint<8> g_in = rgb_in.range(15, 8);
        ap_uint<8> b_in = rgb_in.range(7, 0);
        ap_uint<8> y = enh_luma(rgb_in);

        // ---- line buffers + 3x3 window (identical mechanics to sobel) --------
        ap_uint<2> i_top = phase;
        ap_uint<2> i_mid = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        ap_uint<2> i_bot = (phase == 0) ? ap_uint<2>(2) : ap_uint<2>(phase - 1);

        ap_uint<8> top_v = lbuf[i_top][col];
        ap_uint<8> mid_v = lbuf[i_mid][col];
        lbuf[i_bot][col] = y;

        if (col == 0) {
            wtop[0] = top_v;
            wtop[1] = top_v;
            wtop[2] = top_v;
            wmid[0] = mid_v;
            wmid[1] = mid_v;
            wmid[2] = mid_v;
            wbot[0] = y;
            wbot[1] = y;
            wbot[2] = y;
        } else {
            wtop[2] = wtop[1];
            wtop[1] = wtop[0];
            wtop[0] = top_v;
            wmid[2] = wmid[1];
            wmid[1] = wmid[0];
            wmid[0] = mid_v;
            wbot[2] = wbot[1];
            wbot[1] = wbot[0];
            wbot[0] = y;
        }

        // ---- stage 1: local mean (1-2-1 Gaussian over the same window) -------
        ap_uint<12> lsum = (ap_uint<12>)wtop[0] + (ap_uint<12>)(2 * wtop[1]) + (ap_uint<12>)wtop[2]
                         + (ap_uint<12>)(2 * wmid[0]) + (ap_uint<12>)(4 * wmid[1]) + (ap_uint<12>)(2 * wmid[2])
                         + (ap_uint<12>)wbot[0] + (ap_uint<12>)(2 * wbot[1]) + (ap_uint<12>)wbot[2];
        ap_uint<8> local_mean = (ap_uint<8>)(lsum >> 4);   // sum is 0..4080, >>4 = 0..255

        // ---- stage 2: local contrast boost ----------------------------------
        // y1 = mean + (clarity * (y - mean)) >> 4      (clarity 16 = identity)
        ap_int<10> detail = (ap_int<10>)y - (ap_int<10>)local_mean;   // -255..255
        ap_int<20> prod = (ap_int<20>)clarity * (ap_int<20>)detail;
        ap_int<20> boost = prod >> 4;                                 // arithmetic shift
        ap_int<16> y1 = (ap_int<16>)local_mean + (ap_int<16>)boost;
        ap_uint<8> y1c = enh_clip8(y1);

        // ---- stage 3: two-segment tone curve ---------------------------------
        // below the knee: y * gain_lo / 16 ; above: knee + (y - knee) * gain_hi / 16
        // Gains go through shift/add, not a multiplier - see enh_apply_gain for why.
        ap_int<16> y2;
        if (y1c <= knee) {
            y2 = enh_apply_gain((ap_int<16>)y1c, gain_lo);
        } else {
            ap_int<16> above = (ap_int<16>)y1c - (ap_int<16>)knee;
            y2 = (ap_int<16>)knee + enh_apply_gain(above, gain_hi);
        }
        ap_uint<8> y2c = enh_clip8(y2);

        // ---- stage 4: binarise / invert --------------------------------------
        ap_uint<8> y3 = y2c;
        if (binarize) {
            y3 = (y2c >= thresh) ? ap_uint<8>(255) : ap_uint<8>(0);
        }
        if (invert) {
            y3 = (ap_uint<8>)(255 - y3);
        }

        // ---- stage 5: colour -------------------------------------------------
        // Keep chroma by shifting all three channels by the same delta. In mono
        // mode the tone result replaces the colour outright (what a reader wants
        // when they binarise text).
        ap_int<10> delta = (ap_int<10>)y3 - (ap_int<10>)y;
        ap_uint<8> r_out, g_out, b_out;
        if (mono) {
            r_out = y3;
            g_out = y3;
            b_out = y3;
        } else {
            r_out = enh_clip8((ap_int<16>)r_in + (ap_int<16>)delta);
            g_out = enh_clip8((ap_int<16>)g_in + (ap_int<16>)delta);
            b_out = enh_clip8((ap_int<16>)b_in + (ap_int<16>)delta);
        }

        // ---- split screen: left of split_x stays untouched -------------------
        if (split_x != 0 && (ap_uint<16>)col < split_x) {
            r_out = r_in;
            g_out = g_in;
            b_out = b_in;
        }

        ap_uint<24> rgb_out = ((ap_uint<24>)r_out << 16) | ((ap_uint<24>)g_out << 8) | (ap_uint<24>)b_out;
        ap_uint<ENH_PIX_W> upper = pin.data & ~(ap_uint<ENH_PIX_W>)0xFFFFFF;
        pout.data = upper | (ap_uint<ENH_PIX_W>)rgb_out;

        s_out.write(pout);

        if (pin.last) {
            col = 0;
            phase = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        } else {
            col++;
        }
