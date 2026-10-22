// -----------------------------------------------------------------------------
// tb_enhance_cfg.cpp - C simulation for the memory-configured kernel.
//
// Why this testbench exists
//   The cfg variant never had a C simulation: the note in its build script says the shared include
//   guarantees equivalence with the port-based variant, which is true for the pixel maths but says
//   nothing about the configuration path. The configuration path then turned out to be where a real
//   defect lived (vertical stripes that scaled with the gain), and it has just been rewritten to
//   latch the word once per line. Testing the latch itself costs seconds; discovering a mistake in
//   it after a 40-minute implementation run costs an hour.
//
// What it checks
//   1. A uniform input produces a uniform output - the exact property that failed on the board.
//   2. The output matches the tone curve for the configuration written into word 0.
//   3. Changing the word between frames takes effect (the latch refreshes every line).
//   4. TLAST/TUSER survive the pipeline so the stream stays frame-aligned.
// -----------------------------------------------------------------------------
#include "hls_stream.h"
#include "ap_axi_sdata.h"
#include "ap_int.h"
#include <cstdio>
#include <cstdlib>

#include "enhance.hpp"

static int failures = 0;

static void expect(bool condition, const char* what) {
    if (!condition) {
        std::printf("  FAIL: %s\n", what);
        failures++;
    }
}

// One frame of a uniform grey value, with TLAST on the final pixel of every line.
static void push_frame(enh_stream_t& s, ap_uint<8> grey, int width, int height,
                       bool user_on_first) {
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            enh_pixel_t p;
            p.data = ((ap_uint<ENH_PIX_W>)grey << 16)
                   | ((ap_uint<ENH_PIX_W>)grey << 8)
                   | (ap_uint<ENH_PIX_W>)grey;
            p.keep = ENH_KEEP_ALL;
            p.strb = ENH_KEEP_ALL;
            p.last = (x == width - 1) ? 1 : 0;
            p.user = (user_on_first && x == 0 && y == 0) ? 1 : 0;
            s.write(p);
        }
    }
}

// Drain the frame and return the grey level seen on the last line, plus a uniformity flag.
static ap_uint<8> pop_frame(enh_stream_t& s, int width, int height, int* last_seen,
                            bool* uniform, ap_uint<8>* first_pixel, bool* user_seen) {
    ap_uint<8> sample = 0;
    int min_v = 255, max_v = 0;
    *uniform = true;
    *last_seen = 0;
    *user_seen = false;
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            enh_pixel_t p = s.read();
            ap_uint<8> r = p.data.range(23, 16);
            ap_uint<8> g = p.data.range(15, 8);
            ap_uint<8> b = p.data.range(7, 0);
            if (r != g || g != b) { *uniform = false; }
            int v = (int)r;
            if (v < min_v) min_v = v;
            if (v > max_v) max_v = v;
            if (p.last) (*last_seen)++;
            if (p.user) *user_seen = true;
            if (x == 0 && y == 0) *first_pixel = r;
            sample = r;
        }
    }
    if (max_v - min_v > 1) { *uniform = false; }
    return sample;
}

int main() {
    const int W = 640;
    const int H = 480;

    // word 0: clarity 16 (identity), knee 255, gain_lo 32 (2x), gain_hi 16, no flags
    ap_uint<64> cfg[2];
    cfg[0] = ((ap_uint<64>)16 << 0)     // clarity
           | ((ap_uint<64>)255 << 8)    // knee
           | ((ap_uint<64>)32 << 16)    // gain_lo 2x
           | ((ap_uint<64>)16 << 24);   // gain_hi 1x
    cfg[1] = 0;

    std::printf("cfg word0 = 0x%016llx (gain_lo 2x)\n", (unsigned long long)cfg[0].to_uint64());

    enh_stream_t in, out;

    // ---- frame 1: uniform 64 must come out uniform 128 ------------------------------
    push_frame(in, 64, W, H, true);
    enhance_stream_cfg(in, out, cfg);

    int lasts = 0;
    bool uniform = false;
    bool user_seen = false;
    ap_uint<8> first = 0;
    ap_uint<8> v = pop_frame(out, W, H, &lasts, &uniform, &first, &user_seen);

    std::printf("frame 1: value %d, uniform %d, tlast count %d\n", (int)v, (int)uniform, lasts);
    expect(uniform, "uniform input must give a uniform output (this is what striping breaks)");
    expect(v == 128, "64 * gain_lo(32)/16 should be 128");
    expect(lasts == H, "every line must carry exactly one TLAST");
    expect(user_seen, "TUSER from the input must survive to the output");

    // ---- frame 2: same input with a different word must use the new gain ------------
    cfg[0] = ((ap_uint<64>)16 << 0)
           | ((ap_uint<64>)255 << 8)
           | ((ap_uint<64>)24 << 16)    // 1.5x -> 96
           | ((ap_uint<64>)16 << 24);

    push_frame(in, 64, W, H, false);
    enhance_stream_cfg(in, out, cfg);
    v = pop_frame(out, W, H, &lasts, &uniform, &first, &user_seen);
    std::printf("frame 2: value %d (expected 96)\n", (int)v);
    expect(uniform, "frame 2 must also be uniform");
    expect(v == 96, "64 * gain_lo(24)/16 should be 96 - the latch must refresh");

    // ---- frame 3: identity word must return the input unchanged --------------------
    cfg[0] = ((ap_uint<64>)16 << 0) | ((ap_uint<64>)255 << 8)
           | ((ap_uint<64>)16 << 16) | ((ap_uint<64>)16 << 24);
    push_frame(in, 200, W, H, false);
    enhance_stream_cfg(in, out, cfg);
    v = pop_frame(out, W, H, &lasts, &uniform, &first, &user_seen);
    std::printf("frame 3: value %d (expected 200, identity)\n", (int)v);
    expect(uniform, "identity frame must be uniform");
    expect(v == 200, "identity configuration must pass the input through");

    if (failures == 0) {
        std::printf("ENHANCE CFG TB PASS\n");
        return 0;
    }
    std::printf("ENHANCE CFG TB FAIL (%d checks)\n", failures);
    return 1;
}
