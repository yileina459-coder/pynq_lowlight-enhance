// -----------------------------------------------------------------------------
// sobel_bounded.cpp - Sobel for the DMA path: processes exactly N pixels per call
//
// Why a second variant exists
//   The HDMI variant (sobel.cpp) is a free-running kernel: ap_ctrl_none, an
//   infinite loop, one beat in one beat out. On the board that kernel turned out
//   not to drain when the input stopped: a transfer of 1280 pixels produced
//   fewer than 1280 output beats, so the DMA never saw TLAST and never completed
//   (measurements in docs/dma_investigation.md). For a continuous video stream
//   that is only latency, but for "one transfer per burst" it breaks the framing.
//
//   This variant is invoked with a start/done handshake and a pixel count, so the
//   loop terminates, the pipeline drains inside the call, and every input beat
//   produces an output beat before ap_done rises.
//
// Interface
//   s_in / s_out : AXI4-Stream, 32-bit (low 24 bits = RGB), as before
//   n_pixels     : AXI-Lite scalar, how many pixels this call must process
//   return       : ap_ctrl_hs (ap_start / ap_done), plus the AXI-Lite control
//
// The algorithm, the border policy and the line-buffer state machine are the
// same as sobel.cpp - deliberately identical so a board capture can be compared
// with the same golden model. The state is static so it survives across calls,
// which is what keeps the vertical context when the software sends one row per
// transfer.
// -----------------------------------------------------------------------------
#include "sobel.hpp"

void sobel_bounded(sobel_stream_t& s_in, sobel_stream_t& s_out, int n_pixels) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE s_axilite port = n_pixels bundle = control
#pragma HLS INTERFACE s_axilite port = return bundle = control

    static ap_uint<8> lbuf[3][SOBEL_MAX_W];
#pragma HLS ARRAY_PARTITION variable = lbuf complete dim = 1

    static ap_uint<8> wtop[3];
    static ap_uint<8> wmid[3];
    static ap_uint<8> wbot[3];
#pragma HLS ARRAY_PARTITION variable = wtop complete
#pragma HLS ARRAY_PARTITION variable = wmid complete
#pragma HLS ARRAY_PARTITION variable = wbot complete

    static ap_uint<11> col = 0;
    static ap_uint<2> phase = 0;

loop_pixels:
    for (int i = 0; i < n_pixels; i++) {
#pragma HLS PIPELINE II = 1

        sobel_pixel_t pin = s_in.read();
        sobel_pixel_t pout = pin;

        ap_uint<24> rgb_in = pin.data.range(23, 0);
        ap_uint<8> y = sobel_luma(rgb_in);

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

        ap_int<16> gx = (ap_int<16>)wtop[0] + 2 * (ap_int<16>)wmid[0] +
                        (ap_int<16>)wbot[0] - (ap_int<16>)wtop[2] -
                        2 * (ap_int<16>)wmid[2] - (ap_int<16>)wbot[2];
        ap_int<16> gy = (ap_int<16>)wbot[0] + 2 * (ap_int<16>)wbot[1] +
                        (ap_int<16>)wbot[2] - (ap_int<16>)wtop[0] -
                        2 * (ap_int<16>)wtop[1] - (ap_int<16>)wtop[2];

        ap_int<16> neg_gx = -gx;
        ap_int<16> neg_gy = -gy;
        ap_uint<16> mag = (ap_uint<16>)(gx < 0 ? neg_gx : gx) +
                          (ap_uint<16>)(gy < 0 ? neg_gy : gy);
        ap_uint<8> edge = (mag > 255) ? ap_uint<8>(255) : ap_uint<8>(mag);

        ap_uint<24> rgb_out = ((ap_uint<24>)edge << 16) |
                              ((ap_uint<24>)edge << 8) | (ap_uint<24>)edge;
        ap_uint<SOBEL_PIX_W> upper = pin.data & ~(ap_uint<SOBEL_PIX_W>)0xFFFFFF;
        pout.data = upper | (ap_uint<SOBEL_PIX_W>)rgb_out;

        s_out.write(pout);

        if (pin.last) {
            col = 0;
            phase = (phase == 2) ? ap_uint<2>(0) : ap_uint<2>(phase + 1);
        } else {
            col++;
        }
    }
}
