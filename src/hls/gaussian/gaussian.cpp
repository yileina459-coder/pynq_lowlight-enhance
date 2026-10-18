// -----------------------------------------------------------------------------
// gaussian.cpp - streaming 3x3 Gaussian blur, per-channel RGB
//
// Window generation is the same pattern as sobel.cpp: three line buffers whose
// roles rotate once per line, plus a 3-tap shift register per row, which keeps
// the line buffers at one read and one write per pixel (II=1 in a true dual-port
// BRAM).
//
// The separable form is used to keep the adder tree shallow:
//     h_row = left + 2*centre + right                (per channel)
//     out   = (h_top + 2*h_mid + h_bot) >> 4
// which is exactly the 1-2-1 / 1-2-1 kernel divided by 16.
// -----------------------------------------------------------------------------
#include "gaussian.hpp"

namespace {

// 1-2-1 / 1-2-1 weighted sum of one channel, normalised by 16.
//
// Done as a single 9-tap sum rather than two passes on purpose: the horizontal
// pass would need a 10-bit intermediate per channel, and packing that back into
// 8-bit fields silently truncates (a bug this kernel originally had - the green
// channel read back as 31 instead of 175). One wide accumulator avoids it.
static inline ap_uint<8> gauss_tap(ap_uint<8> left, ap_uint<8> mid, ap_uint<8> right,
                                   ap_uint<8> mleft, ap_uint<8> mmid, ap_uint<8> mright,
                                   ap_uint<8> bleft, ap_uint<8> bmid, ap_uint<8> bright) {
#pragma HLS INLINE
    ap_uint<12> s = (ap_uint<12>)left + ((ap_uint<12>)mid << 1) + (ap_uint<12>)right
                  + ((ap_uint<12>)mleft << 1) + ((ap_uint<12>)mmid << 2) + ((ap_uint<12>)mright << 1)
                  + (ap_uint<12>)bleft + ((ap_uint<12>)bmid << 1) + (ap_uint<12>)bright;
    return (ap_uint<8>)(s >> 4);
}

} // namespace

void gaussian_stream(gauss_stream_t& s_in, gauss_stream_t& s_out) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE ap_ctrl_none port = return

    static ap_uint<24> lbuf[3][GAUSS_MAX_W];
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
    for (int _emu = 0; _emu < GAUSS_EMU_PIXELS; _emu++) {
#endif
#pragma HLS PIPELINE II = 1

        gauss_pixel_t pin = s_in.read();
        gauss_pixel_t pout = pin;

        ap_uint<24> rgb = pin.data.range(23, 0);

        ap_uint<2> i_top = phase;
        ap_uint<2> i_mid = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        ap_uint<2> i_bot = (phase == 0) ? ap_uint<2>(2) : ap_uint<2>(phase - 1);

        ap_uint<24> top_v = lbuf[i_top][col];
        ap_uint<24> mid_v = lbuf[i_mid][col];
        lbuf[i_bot][col] = rgb;

        // Shift the window right; at the start of a line fill it with the first
        // pixel (left-edge replicate, same policy as Sobel).
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

        // Window columns: index 2 is c-2 (left), 1 is c-1, 0 is c (right).
        ap_uint<24> blur = 0;
        for (int c = 0; c < 3; c++) {
#pragma HLS UNROLL
            ap_uint<8> ch = gauss_tap(
                wtop[2].range(c * 8 + 7, c * 8), wtop[1].range(c * 8 + 7, c * 8),
                wtop[0].range(c * 8 + 7, c * 8),
                wmid[2].range(c * 8 + 7, c * 8), wmid[1].range(c * 8 + 7, c * 8),
                wmid[0].range(c * 8 + 7, c * 8),
                wbot[2].range(c * 8 + 7, c * 8), wbot[1].range(c * 8 + 7, c * 8),
                wbot[0].range(c * 8 + 7, c * 8));
            blur.range(c * 8 + 7, c * 8) = ch;
        }

        ap_uint<GAUSS_PIX_W> upper = pin.data & ~(ap_uint<GAUSS_PIX_W>)0xFFFFFF;
        pout.data = upper | (ap_uint<GAUSS_PIX_W>)blur;

        s_out.write(pout);

        if (pin.last) {
            col = 0;
            phase = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        } else {
            col++;
        }
    }
}
