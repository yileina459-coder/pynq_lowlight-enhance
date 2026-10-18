// -----------------------------------------------------------------------------
// sharpen.hpp - streaming 3x3 sharpen (centre-weighted Laplacian)
//
//   kernel:   0 -1  0
//            -1  5 -1        out = 5*centre - (up + down + left + right)
//             0 -1  0
//
// Per channel, saturated to 0..255: the result can go negative on the bright
// side of an edge, and clamping (not wrapping) is what the software reference
// does, so the two agree bit for bit.
//
// Window generation and border policy are identical to the Sobel and Gaussian
// kernels: rotating line buffers, per-row 3-tap shift registers, horizontal
// replicate at the left edge, vertical rows taken from the line buffers.
// -----------------------------------------------------------------------------
#ifndef SHARPEN_HPP
#define SHARPEN_HPP

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>

#ifndef SHARP_PIX_W
#define SHARP_PIX_W 32
#endif

#ifndef SHARP_MAX_W
#define SHARP_MAX_W 1920
#endif

#ifndef SHARP_EMU_PIXELS
#define SHARP_EMU_PIXELS (64 * 48 * 3)
#endif

typedef ap_axiu<SHARP_PIX_W, 1, 1, 1> sharp_pixel_t;
typedef hls::stream<sharp_pixel_t> sharp_stream_t;

static const int SHARP_KEEP_ALL = (1 << (SHARP_PIX_W / 8)) - 1;

void sharpen_stream(sharp_stream_t& s_in, sharp_stream_t& s_out);

#endif // SHARPEN_HPP
