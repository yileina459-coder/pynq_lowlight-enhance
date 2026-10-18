// -----------------------------------------------------------------------------
// gaussian.hpp - streaming 3x3 Gaussian blur
//
// Same window pattern as sobel.cpp (three rotating line buffers + per-row 3-tap
// shift registers, one pixel per clock), but the tap weights are 1-2-1 in both
// directions and the result is per-channel colour, not a luma gradient.
//
//   weights:  1 2 1        sum of weights = 16, so the output is  sum >> 4
//             2 4 2
//             1 2 1
//
// Border policy is identical to the Sobel kernel so a single golden-reference
// tool can verify both: horizontal replicate at the left edge, vertical rows
// taken from the line buffers (previous frame's last lines during warm-up).
// -----------------------------------------------------------------------------
#ifndef GAUSSIAN_HPP
#define GAUSSIAN_HPP

#include <ap_axi_sdata.h>
#include <ap_int.h>
#include <hls_stream.h>

#ifndef GAUSS_PIX_W
#define GAUSS_PIX_W 32
#endif

#ifndef GAUSS_MAX_W
#define GAUSS_MAX_W 1920
#endif

#ifndef GAUSS_EMU_PIXELS
#define GAUSS_EMU_PIXELS (64 * 48 * 3)
#endif

typedef ap_axiu<GAUSS_PIX_W, 1, 1, 1> gauss_pixel_t;
typedef hls::stream<gauss_pixel_t> gauss_stream_t;

static const int GAUSS_KEEP_ALL = (1 << (GAUSS_PIX_W / 8)) - 1;

void gaussian_stream(gauss_stream_t& s_in, gauss_stream_t& s_out);

#endif // GAUSSIAN_HPP
