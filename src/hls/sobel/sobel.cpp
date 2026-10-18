// -----------------------------------------------------------------------------
// sobel.cpp - streaming Sobel edge detector (3x3, |Gx|+|Gy|)
//
// Structure (one pixel per clock, II=1):
//   * three line buffers, 8-bit luma, SOBEL_MAX_W wide, rotating roles
//     top = row r-2, mid = row r-1, bot = row r
//   * per-row 3-tap shift registers build the 3x3 window, so each line buffer
//     is touched once per pixel (one read, one write) - that fits in a true
//     dual-port BRAM and keeps II=1 reachable
//
// The kernel is a free-running stream processor in hardware (ap_ctrl_none), so
// it has no notion of "one image per call". C simulation needs a finite number
// of pixels, hence the SOBEL_EMU_PIXELS bound in the non-synthesis build.
// -----------------------------------------------------------------------------
#include "sobel.hpp"

void sobel_stream(sobel_stream_t& s_in, sobel_stream_t& s_out) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE ap_ctrl_none port = return

    // Line buffers: [row role][column]. Complete partition on the row role
    // turns the 3 rows into 3 independent memories; the per-pixel role lookup
    // becomes a small mux instead of a variable array index into one big BRAM.
    static ap_uint<8> lbuf[3][SOBEL_MAX_W];
#pragma HLS ARRAY_PARTITION variable = lbuf complete dim = 1

    // 3-tap shift registers, one per row of the window.
    static ap_uint<8> wtop[3];
    static ap_uint<8> wmid[3];
    static ap_uint<8> wbot[3];
#pragma HLS ARRAY_PARTITION variable = wtop complete
#pragma HLS ARRAY_PARTITION variable = wmid complete
#pragma HLS ARRAY_PARTITION variable = wbot complete

    // Column counter and the role rotation, both persistent across lines.
    static ap_uint<11> col = 0;
    static ap_uint<2> phase = 0;

#ifdef __SYNTHESIS__
    while (1) {
#else
    for (int _emu = 0; _emu < SOBEL_EMU_PIXELS; _emu++) {
#endif
#pragma HLS PIPELINE II = 1

        sobel_pixel_t pin = s_in.read();
        sobel_pixel_t pout = pin;   // carries keep/strb/user/last/id/dest through

        ap_uint<8> y = sobel_luma(pin.data);

        // Row roles for this pixel.
        ap_uint<2> i_top = phase;
        ap_uint<2> i_mid = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        ap_uint<2> i_bot = (phase == 0) ? ap_uint<2>(2) : ap_uint<2>(phase - 1);

        ap_uint<8> top_v = lbuf[i_top][col];
        ap_uint<8> mid_v = lbuf[i_mid][col];
        lbuf[i_bot][col] = y;       // recycle the oldest row buffer with row r

        // Shift the 3x3 window right by one column. At the start of a line the
        // whole window is filled with the first pixel, which implements the
        // left-edge replicate policy documented in sobel.hpp.
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

        // Gx = right column - left column, Gy = bottom row - top row.
        ap_int<16> gx = (ap_int<16>)wtop[0] + 2 * (ap_int<16>)wmid[0] +
                        (ap_int<16>)wbot[0] - (ap_int<16>)wtop[2] -
                        2 * (ap_int<16>)wmid[2] - (ap_int<16>)wbot[2];
        ap_int<16> gy = (ap_int<16>)wbot[0] + 2 * (ap_int<16>)wbot[1] +
                        (ap_int<16>)wbot[2] - (ap_int<16>)wtop[0] -
                        2 * (ap_int<16>)wtop[1] - (ap_int<16>)wtop[2];

        // |Gx| + |Gy| with explicit temporaries: a bare "gx < 0 ? -gx : gx"
        // is an ambiguous conditional for ap_int (the negation widens by a bit).
        ap_int<16> neg_gx = -gx;
        ap_int<16> neg_gy = -gy;
        ap_uint<16> mag = (ap_uint<16>)(gx < 0 ? neg_gx : gx) +
                          (ap_uint<16>)(gy < 0 ? neg_gy : gy);
        ap_uint<8> edge = (mag > 255) ? ap_uint<8>(255) : ap_uint<8>(mag);

        // Replicate the edge value to R, G and B so the result is visible on a
        // normal RGB display without a further colour-space stage.
        pout.data = ((ap_uint<24>)edge << 16) | ((ap_uint<24>)edge << 8) | (ap_uint<24>)edge;

        s_out.write(pout);

        // End of line: restart the column counter and rotate the row roles.
        if (pin.last) {
            col = 0;
            phase = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        } else {
            col++;
        }
    }
}
