// -----------------------------------------------------------------------------
// enhance_bounded.cpp - enhance for the AXI-DMA path: exactly N pixels per call
//
// Why a second variant exists
//   enhance.cpp is a free-running stream processor (ap_ctrl_none + while(1)),
//   which is what the HDMI path needs. On the DMA path that shape has a fatal
//   property we measured on the board with Sobel: when the input stops, the
//   pipeline stops at the read port and the last beats never come out, so the
//   AXI-DMA transfer can never be closed by TLAST (docs/dma_investigation.md).
//
//   This variant is invoked with ap_start / ap_done and a pixel count, so the
//   loop terminates and everything drains inside the call. It also takes the
//   59 config bits as AXI-Lite scalars, which is how the PS sets the presets at
//   run time without an axi_gpio.
//
// Keep the arithmetic in sync with enhance.cpp
//   The stage-by-stage maths below is a copy of enhance_stream(), deliberately
//   unchanged so that both variants remain bit-identical to the same golden
//   model (sim/enhance/golden_enhance.py). If one is edited, edit both - the
//   board test compares against numpy with zero tolerance, so a divergence
//   shows up immediately rather than silently.
//
// Register map (AXI-Lite, byte offsets)
//   0x00 ctrl (bit0 ap_start, bit1 ap_done, bit2 ap_idle, bit3 ap_ready)
//   0x10 n_pixels   0x18 line_width
//   0x20 clarity    0x24 knee      0x28 gain_lo   0x2c gain_hi
//   0x30 thresh     0x34 binarize  0x38 invert     0x3c mono
//   0x40 split_x
// -----------------------------------------------------------------------------
#include "enhance.hpp"

void enhance_bounded(enh_stream_t& s_in,
                     enh_stream_t& s_out,
                     ap_uint<32> n_pixels,
                     ap_uint<16> line_width,
                     ap_uint<8> clarity,
                     ap_uint<8> knee,
                     ap_uint<8> gain_lo,
                     ap_uint<8> gain_hi,
                     ap_uint<8> thresh,
                     ap_uint<1> binarize,
                     ap_uint<1> invert,
                     ap_uint<1> mono,
                     ap_uint<16> split_x) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE s_axilite port = n_pixels bundle = ctrl
#pragma HLS INTERFACE s_axilite port = line_width bundle = ctrl
#pragma HLS INTERFACE s_axilite port = clarity bundle = ctrl
#pragma HLS INTERFACE s_axilite port = knee bundle = ctrl
#pragma HLS INTERFACE s_axilite port = gain_lo bundle = ctrl
#pragma HLS INTERFACE s_axilite port = gain_hi bundle = ctrl
#pragma HLS INTERFACE s_axilite port = thresh bundle = ctrl
#pragma HLS INTERFACE s_axilite port = binarize bundle = ctrl
#pragma HLS INTERFACE s_axilite port = invert bundle = ctrl
#pragma HLS INTERFACE s_axilite port = mono bundle = ctrl
#pragma HLS INTERFACE s_axilite port = split_x bundle = ctrl
#pragma HLS INTERFACE s_axilite port = return bundle = ctrl

    static ap_uint<8> lbuf[3][ENH_MAX_W];
#pragma HLS ARRAY_PARTITION variable = lbuf complete dim = 1

    static ap_uint<8> wtop[3];
    static ap_uint<8> wmid[3];
    static ap_uint<8> wbot[3];
#pragma HLS ARRAY_PARTITION variable = wtop complete
#pragma HLS ARRAY_PARTITION variable = wmid complete
#pragma HLS ARRAY_PARTITION variable = wbot complete

    static ap_uint<12> col = 0;
    static ap_uint<2> phase = 0;

loop_pixels:
    for (ap_uint<32> i = 0; i < n_pixels; i++) {
#pragma HLS PIPELINE II = 1

        enh_pixel_t pin = s_in.read();
        enh_pixel_t pout = pin;

        ap_uint<24> rgb_in = pin.data.range(23, 0);
        ap_uint<8> r_in = rgb_in.range(23, 16);
        ap_uint<8> g_in = rgb_in.range(15, 8);
        ap_uint<8> b_in = rgb_in.range(7, 0);
        ap_uint<8> y = enh_luma(rgb_in);

        // ---- line buffers + 3x3 window --------------------------------------
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

        // ---- stage 1: local mean --------------------------------------------
        ap_uint<12> lsum = (ap_uint<12>)wtop[0] + (ap_uint<12>)(2 * wtop[1]) + (ap_uint<12>)wtop[2]
                         + (ap_uint<12>)(2 * wmid[0]) + (ap_uint<12>)(4 * wmid[1]) + (ap_uint<12>)(2 * wmid[2])
                         + (ap_uint<12>)wbot[0] + (ap_uint<12>)(2 * wbot[1]) + (ap_uint<12>)wbot[2];
        ap_uint<8> local_mean = (ap_uint<8>)(lsum >> 4);

        // ---- stage 2: local contrast boost ----------------------------------
        ap_int<10> detail = (ap_int<10>)y - (ap_int<10>)local_mean;
        ap_int<20> prod = (ap_int<20>)clarity * (ap_int<20>)detail;
        ap_int<20> boost = prod >> 4;
        ap_int<16> y1 = (ap_int<16>)local_mean + (ap_int<16>)boost;
        ap_uint<8> y1c = enh_clip8(y1);

        // ---- stage 3: two-segment tone curve --------------------------------
        ap_int<16> y2;
        if (y1c <= knee) {
            y2 = ((ap_int<16>)y1c * (ap_int<16>)gain_lo) >> 4;
        } else {
            ap_int<16> above = (ap_int<16>)y1c - (ap_int<16>)knee;
            y2 = (ap_int<16>)knee + (((ap_int<16>)above * (ap_int<16>)gain_hi) >> 4);
        }
        ap_uint<8> y2c = enh_clip8(y2);

        // ---- stage 4: binarise / invert -------------------------------------
        ap_uint<8> y3 = y2c;
        if (binarize) {
            y3 = (y2c >= thresh) ? ap_uint<8>(255) : ap_uint<8>(0);
        }
        if (invert) {
            y3 = (ap_uint<8>)(255 - y3);
        }

        // ---- stage 5: colour -------------------------------------------------
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

        // ---- split screen ----------------------------------------------------
        if (split_x != 0 && (ap_uint<16>)col < split_x) {
            r_out = r_in;
            g_out = g_in;
            b_out = b_in;
        }

        ap_uint<24> rgb_out = ((ap_uint<24>)r_out << 16) | ((ap_uint<24>)g_out << 8) | (ap_uint<24>)b_out;
        ap_uint<ENH_PIX_W> upper = pin.data & ~(ap_uint<ENH_PIX_W>)0xFFFFFF;
        pout.data = upper | (ap_uint<ENH_PIX_W>)rgb_out;

        s_out.write(pout);

        // Line boundary: counted when line_width is given (a whole-frame transfer
        // only carries TLAST at the very end), otherwise taken from TLAST.
        if (line_width != 0) {
            if ((ap_uint<16>)col + 1 >= line_width) {
                col = 0;
                phase = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
            } else {
                col++;
            }
        } else if (pin.last) {
            col = 0;
            phase = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        } else {
            col++;
        }
    }
}
