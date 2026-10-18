// -----------------------------------------------------------------------------
// sharpen.cpp - streaming 3x3 sharpen, per-channel RGB
//
// out = 5*centre - (up + down + left + right), saturated to 0..255.
//
// Same window machinery as gaussian.cpp / sobel.cpp (rotating line buffers plus
// per-row 3-tap shift registers, II=1).
// -----------------------------------------------------------------------------
#include "sharpen.hpp"

namespace {

// One channel, clamped rather than wrapped.
static inline ap_uint<8> sharpen_tap(ap_uint<8> centre,
                                     ap_uint<8> up, ap_uint<8> down,
                                     ap_uint<8> left, ap_uint<8> right) {
#pragma HLS INLINE
    ap_int<12> acc = ((ap_int<12>)centre << 2) + (ap_int<12>)centre
                   - (ap_int<12>)up - (ap_int<12>)down
                   - (ap_int<12>)left - (ap_int<12>)right;
    if (acc < 0) {
        return (ap_uint<8>)0;
    }
    if (acc > 255) {
        return (ap_uint<8>)255;
    }
    return (ap_uint<8>)acc;
}

} // namespace

void sharpen_stream(sharp_stream_t& s_in, sharp_stream_t& s_out) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE ap_ctrl_none port = return

    static ap_uint<24> lbuf[3][SHARP_MAX_W];
#pragma HLS ARRAY_PARTITION variable = lbuf complete dim = 1

    static ap_uint<24> wtop[3];
    static ap_uint<24> wmid[3];
    static ap_uint<24> wbot[3];
#pragma HLS ARRAY_PARTITION variable = wtop complete
#pragma HLS ARRAY_PARTITION variable = wmid complete
#pragma HLS ARRAY_PARTITION variable = wbot complete

    static ap_uint<11> col = 0;
    static ap_uint<2> phase = 0;

#ifdef __SYNTHESIS__
    while (1) {
#else
    for (int _emu = 0; _emu < SHARP_EMU_PIXELS; _emu++) {
#endif
#pragma HLS PIPELINE II = 1

        sharp_pixel_t pin = s_in.read();
        sharp_pixel_t pout = pin;

        ap_uint<24> rgb = pin.data.range(23, 0);

        ap_uint<2> i_top = phase;
        ap_uint<2> i_mid = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        ap_uint<2> i_bot = (phase == 0) ? ap_uint<2>(2) : ap_uint<2>(phase - 1);

        ap_uint<24> top_v = lbuf[i_top][col];
        ap_uint<24> mid_v = lbuf[i_mid][col];
        lbuf[i_bot][col] = rgb;

        if (col == 0) {
            for (int k = 0; k < 3; k++) {
#pragma HLS UNROLL
                wtop[k] = top_v;
                wmid[k] = mid_v;
                wbot[k] = rgb;
            }
        } else {
            for (int k = 2; k > 0; k--) {
#pragma HLS UNROLL
                wtop[k] = wtop[k - 1];
                wmid[k] = wmid[k - 1];
                wbot[k] = wbot[k - 1];
            }
            wtop[0] = top_v;
            wmid[0] = mid_v;
            wbot[0] = rgb;
        }

        // Window columns: index 2 is left (c-2), 1 is centre (c-1), 0 is right (c).
        ap_uint<24> sharp = 0;
        for (int c = 0; c < 3; c++) {
#pragma HLS UNROLL
            ap_uint<8> centre = wmid[1].range(c * 8 + 7, c * 8);
            ap_uint<8> up = wtop[1].range(c * 8 + 7, c * 8);
            ap_uint<8> down = wbot[1].range(c * 8 + 7, c * 8);
            ap_uint<8> left = wmid[2].range(c * 8 + 7, c * 8);
            ap_uint<8> right = wmid[0].range(c * 8 + 7, c * 8);
            sharp.range(c * 8 + 7, c * 8) = sharpen_tap(centre, up, down, left, right);
        }

        ap_uint<SHARP_PIX_W> upper = pin.data & ~(ap_uint<SHARP_PIX_W>)0xFFFFFF;
        pout.data = upper | (ap_uint<SHARP_PIX_W>)sharp;

        s_out.write(pout);

        if (pin.last) {
            col = 0;
            phase = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        } else {
            col++;
        }
    }
}
