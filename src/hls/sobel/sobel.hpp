// -----------------------------------------------------------------------------
// sobel.hpp - shared definitions for the streaming Sobel edge detector
//
// Pixel format: AXI4-Stream of 24-bit RGB (matches PYNQ's pixel_pack output,
// i.e. one pixel per beat, 24 bits used, keep = 0b111). Colour is packed as
// {R[7:0], G[7:0], B[7:0]}.
//
// Border policy is defined here, not left to chance, because the testbench
// golden model and the Python reference must match the hardware bit-exactly:
//   * vertical  : the three rows are (r-2, r-1, r), using the line buffers,
//                 so the very first two lines of the stream wrap to whatever
//                 the buffers held before (zeros at power-up, the previous
//                 frame's last lines afterwards). For a continuous video
//                 stream this is the intended behaviour.
//   * horizontal: at the left edge the window is replicated, i.e. the three
//                 window columns are (max(c-2,0), max(c-1,0), c). The output
//                 beat at column c therefore corresponds to input column c-1.
// -----------------------------------------------------------------------------
#ifndef SOBEL_HPP
#define SOBEL_HPP

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>

// Widest supported line, in pixels. 1920 covers 1080p; 720p only needs 1280.
// The line buffers are sized by this, so it is the main BRAM budget knob.
#ifndef SOBEL_MAX_W
#define SOBEL_MAX_W 1920
#endif

// Number of pixels the C simulation feeds through the kernel. The kernel is an
// infinite stream processor in hardware (ap_ctrl_none), so C simulation needs a
// finite stand-in; the testbench overrides this to match its test image.
#ifndef SOBEL_EMU_PIXELS
#define SOBEL_EMU_PIXELS (64 * 48 * 3)
#endif

typedef ap_axiu<24, 1, 1, 1> sobel_pixel_t;
typedef hls::stream<sobel_pixel_t> sobel_stream_t;

// Luma used for the gradient: BT.601-ish integer approximation,
//   Y = (77*R + 150*G + 29*B) >> 8
// Chosen over floating point so that hardware and the golden model agree
// exactly, with no rounding-mode ambiguity.
static inline ap_uint<8> sobel_luma(ap_uint<24> rgb) {
#pragma HLS INLINE
    ap_uint<8> r = rgb.range(23, 16);
    ap_uint<8> g = rgb.range(15, 8);
    ap_uint<8> b = rgb.range(7, 0);
    ap_uint<16> acc = (ap_uint<16>)r * 77 + (ap_uint<16>)g * 150 + (ap_uint<16>)b * 29;
    return (ap_uint<8>)(acc >> 8);
}

void sobel_stream(sobel_stream_t& s_in, sobel_stream_t& s_out);

#endif // SOBEL_HPP
