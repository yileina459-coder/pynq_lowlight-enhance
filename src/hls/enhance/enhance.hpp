// -----------------------------------------------------------------------------
// enhance.hpp - streaming low-light / low-vision image enhancer (3x3, II=1)
//
// Why this kernel exists
//   A low-vision aid is not judged by frame rate but by end-to-end latency and
//   by whether the picture is legible. This kernel does the whole enhancement
//   chain while a pixel flows through, with no frame buffer at all:
//
//       local contrast  ->  tone curve  ->  binarise / invert  ->  colour
//
//   Every stage is integer only, so the numpy golden model, the C++ golden model
//   in the testbench and the hardware are bit-exact by construction.
//
// Pixel format
//   Same as sobel.hpp: AXI4-Stream, one pixel per beat, low 24 bits carry
//   {R[7:0], G[7:0], B[7:0]}, all higher bits pass through untouched.
//
// Border policy (identical to sobel.hpp, so both operators can be chained)
//   * vertical  : rows (r-2, r-1, r) live in the line buffers; the first two
//                 lines of a stream wrap to whatever the buffers held before.
//   * horizontal: at the left edge the window is replicated, i.e. the window
//                 columns are (max(c-2,0), max(c-1,0), c).
//
// Note on alignment
//   The local mean is the mean of the window ending at the current pixel, so it
//   is centred half a pixel to the left of the pixel it is subtracted from. That
//   is a 1-pixel horizontal bias in the clarity term - invisible at 720p, and
//   modelled identically by both golden models, so nothing silently disagrees.
//
// Configuration (59 bits total, plain ports for now)
//   clarity : local contrast gain, 16 = unity, 24 = 1.5x, 32 = 2x
//   knee    : tone-curve breakpoint (0..255)
//   gain_lo : slope below the knee, /16  (16 = unity, 24 = brighten shadows)
//   gain_hi : slope above the knee, /16  (12 = tame highlights)
//   thresh  : binarisation threshold
//   binarize / invert / mono : output shaping flags
//   split_x : if non-zero, output the untouched pixel for columns < split_x
//             (a split-screen comparison that costs no extra hardware, because
//             the column counter already exists)
//
// For the block design these ports are best driven from one axi_gpio dual
// channel (2 x 32 bit = 64 bit > 59 bit), which avoids touching AXI-Lite in the
// kernel while the design is still being brought up.
// -----------------------------------------------------------------------------
#ifndef ENHANCE_HPP
#define ENHANCE_HPP

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>

// Data bus width: 32 matches AXI DMA / VDMA words; 24 matches pixel_pack.
#ifndef ENH_PIX_W
#define ENH_PIX_W 32
#endif

// Widest supported line, in pixels. Drives the BRAM budget of the line buffers.
#ifndef ENH_MAX_W
#define ENH_MAX_W 1920
#endif

// Pixels pushed through in C simulation. Hardware is an infinite stream
// processor (ap_ctrl_none); this is the finite stand-in for C simulation only.
#ifndef ENH_EMU_PIXELS
#define ENH_EMU_PIXELS (64 * 48 * 3)
#endif

// -----------------------------------------------------------------------------
// enh_apply_gain - the tone curve's gain, without a multiplier.
//
// Why not just multiply
//   y * gain_lo >> 4 is the obvious form and it is what the C model uses, but on the board every
//   preset with gain != 1.0 produced vertical stripes with a period of about three pixels, identical
//   on every row, amplitude proportional to the gain (measured std 0.23 at 1.0x, 2.97 at 1.06x,
//   21.98 at 1.5x). The C simulation of the same code is uniform, latching the configuration once
//   per line did not help, and neither did giving the pipeline two clocks - so the suspicion falls on
//   how the multiply itself ended up in hardware.
//
//   This version uses shifts and adds only, which cannot involve a DSP block and cannot depend on
//   the multiplier's internal pipelining. The supported gains are the ones the presets use; anything
//   else passes through unchanged, which is a visible, honest fallback rather than a silent one.
// -----------------------------------------------------------------------------
inline ap_int<16> enh_apply_gain(ap_int<16> v, ap_uint<8> gain) {
#pragma HLS INLINE
    switch ((int)gain) {
        case 16: return v;                                   // 1.00x
        case 20: return v + (v >> 2);                        // 1.25x
        case 24: return v + (v >> 1);                        // 1.50x
        case 28: return v + (v >> 1) + (v >> 2);             // 1.75x
        case 32: return v << 1;                              // 2.00x
        case 40: return (v << 1) + (v >> 1);                 // 2.50x
        case 48: return (v << 1) + v;                        // 3.00x
        case 56: return (v << 1) + v + (v >> 1);             // 3.50x
        case 64: return v << 2;                              // 4.00x
        case 72: return (v << 2) + (v >> 1);                 // 4.50x
        case 80: return (v << 2) + v;                        // 5.00x
        case 88: return (v << 2) + v + (v >> 1);             // 5.50x
        default: return v;                                   // unsupported gain: identity
    }
}

typedef ap_axiu<ENH_PIX_W, 1, 1, 1> enh_pixel_t;
typedef hls::stream<enh_pixel_t> enh_stream_t;

static const int ENH_KEEP_ALL = (1 << (ENH_PIX_W / 8)) - 1;

// BT.601-ish integer luma, identical to sobel_luma().
static inline ap_uint<8> enh_luma(ap_uint<24> rgb) {
#pragma HLS INLINE
    ap_uint<8> r = rgb.range(23, 16);
    ap_uint<8> g = rgb.range(15, 8);
    ap_uint<8> b = rgb.range(7, 0);
    ap_uint<16> acc = (ap_uint<16>)r * 77 + (ap_uint<16>)g * 150 + (ap_uint<16>)b * 29;
    return (ap_uint<8>)(acc >> 8);
}

// Saturating cast. Written with explicit branches rather than a ternary: a bare
// "v < 0 ? 0 : v" on ap_int is an ambiguous conditional, which is exactly the
// kind of thing that has bitten this project before.
static inline ap_uint<8> enh_clip8(ap_int<16> v) {
#pragma HLS INLINE
    if (v < 0) return (ap_uint<8>)0;
    if (v > 255) return (ap_uint<8>)255;
    return (ap_uint<8>)v;
}

void enhance_stream(enh_stream_t& s_in,
                    enh_stream_t& s_out,
                    ap_uint<8> clarity,
                    ap_uint<8> knee,
                    ap_uint<8> gain_lo,
                    ap_uint<8> gain_hi,
                    ap_uint<8> thresh,
                    ap_uint<1> binarize,
                    ap_uint<1> invert,
                    ap_uint<1> mono,
                    ap_uint<16> split_x);

// Same pipeline, configuration read from a BRAM port on every pixel instead of arriving on
// plain ports. Used by the HDMI overlay so a preset switch does not need a kernel reset.
void enhance_stream_cfg(enh_stream_t& s_in,
                        enh_stream_t& s_out,
                        ap_uint<64> cfg[2]);

#endif // ENHANCE_HPP
