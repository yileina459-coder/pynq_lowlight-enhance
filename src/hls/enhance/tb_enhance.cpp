// -----------------------------------------------------------------------------
// tb_enhance.cpp - C simulation testbench for enhance_stream
//
// What it proves
//   1. one output beat per input beat, with the AXI-Stream side channels
//      (last / user / keep / strb) untouched
//   2. the whole chain - local contrast, tone curve, binarise/invert, colour
//      shift, split screen - matches an independently written golden model
//      bit for bit, not just "looks similar"
//   3. the line-buffer rotation survives frame boundaries (frame 3 is checked,
//      by which time the row roles and the previous frame's tail are steady)
//
// Two configurations are pushed through the same kernel so that every code path
// is covered:
//   A: clarity boost + split screen, colour preserved
//   B: flat clarity + two-segment tone curve + binarise + invert + mono
//
// Image height is a multiple of 3 on purpose: the row-role phase advances once
// per line, so H % 3 == 0 returns the phase to 0 at every frame boundary and the
// golden model can use plain circular vertical indexing.
// -----------------------------------------------------------------------------
#include "enhance.hpp"

#include <cstdio>

#define TB_W 64
#define TB_H 48
#define TB_FRAMES 3

struct Cfg {
    int clarity, knee, glo, ghi, thr, bin, inv, mono, split;
};

// Arithmetic shift right by 4 with floor semantics, i.e. exactly what ap_int's
// ">> 4" does. Written out so the golden model does not depend on the platform's
// choice for right-shifting a negative int.
static int ashr4(int v) {
    return (v >= 0) ? (v >> 4) : -(((-v) + 15) >> 4);
}

static int clip8(int v) {
    if (v < 0) return 0;
    if (v > 255) return 255;
    return v;
}

static ap_uint<8> img[TB_H][TB_W];          // luma of the source frame
static unsigned char rgb[TB_H][TB_W][3];    // source colour, for the stream
static unsigned char got[TB_H][TB_W][3];
static unsigned char gold[TB_H][TB_W][3];

static unsigned luma_ref(unsigned r, unsigned g, unsigned b) {
    return (77u * r + 150u * g + 29u * b) >> 8;
}

// Deterministic image with a dark half and a bright half: the left third is
// near-black (exercises the shadow slope of the tone curve and makes the local
// contrast boost visible), the middle has a fine checker (exercises the 3x3
// mean), the right third is a ramp with a hard-edged block.
static void build_image() {
    for (int y = 0; y < TB_H; y++) {
        for (int x = 0; x < TB_W; x++) {
            unsigned r, g, b;
            if (x < 20) {
                r = (unsigned)(8 + ((x * 3 + y) & 0x1f));
                g = (unsigned)(6 + ((x + y * 2) & 0x1f));
                b = (unsigned)(4 + ((y * 3) & 0x1f));
            } else if (x < 42) {
                if (((x >> 2) + (y >> 2)) & 1) {
                    r = (unsigned)((x * 4) & 0xff);
                    g = (unsigned)((y * 5) & 0xff);
                    b = (unsigned)((x * y) & 0xff);
                } else {
                    r = 220; g = 210; b = 200;
                }
            } else if (y >= 12 && y < 30) {
                r = 235; g = 235; b = 235;
            } else {
                r = (unsigned)((x * 2 + y) & 0xff);
                g = (unsigned)((y * 3) & 0xff);
                b = (unsigned)((x ^ y) & 0xff);
            }
            rgb[y][x][0] = (unsigned char)r;
            rgb[y][x][1] = (unsigned char)g;
            rgb[y][x][2] = (unsigned char)b;
            img[y][x] = (ap_uint<8>)luma_ref(r, g, b);
        }
    }
}

// Golden model: same steps, plain nested loops over the whole frame. Deliberately
// a different code path from the kernel, which walks the stream with rotating
// buffers - that is the point of a golden model.
static void build_golden(const Cfg& g, unsigned char out[TB_H][TB_W][3]) {
    for (int r = 0; r < TB_H; r++) {
        int r0 = (r - 2 + TB_H) % TB_H;
        int r1 = (r - 1 + TB_H) % TB_H;
        int r2 = r;
        for (int c = 0; c < TB_W; c++) {
            int c0 = (c - 2 < 0) ? 0 : c - 2;
            int c1 = (c - 1 < 0) ? 0 : c - 1;
            int c2 = c;

            int y = img[r][c];

            // 1-2-1 local mean over the same window the kernel sees.
            int m = (int)img[r0][c0] + 2 * (int)img[r0][c1] + (int)img[r0][c2]
                  + 2 * (int)img[r1][c0] + 4 * (int)img[r1][c1] + 2 * (int)img[r1][c2]
                  + (int)img[r2][c0] + 2 * (int)img[r2][c1] + (int)img[r2][c2];
            m >>= 4;

            // local contrast
            int d = y - m;
            int y1 = clip8(m + ashr4(g.clarity * d));

            // two-segment tone curve
            int y2;
            if (y1 <= g.knee) {
                y2 = ashr4(y1 * g.glo);
            } else {
                y2 = g.knee + ashr4((y1 - g.knee) * g.ghi);
            }
            y2 = clip8(y2);

            // binarise / invert
            int y3 = y2;
            if (g.bin) y3 = (y3 >= g.thr) ? 255 : 0;
            if (g.inv) y3 = 255 - y3;

            // colour
            int delta = y3 - y;
            int ro, go, bo;
            if (g.mono) {
                ro = go = bo = y3;
            } else {
                ro = clip8((int)rgb[r][c][0] + delta);
                go = clip8((int)rgb[r][c][1] + delta);
                bo = clip8((int)rgb[r][c][2] + delta);
            }

            // split screen
            if (g.split != 0 && c < g.split) {
                ro = rgb[r][c][0];
                go = rgb[r][c][1];
                bo = rgb[r][c][2];
            }

            out[r][c][0] = (unsigned char)ro;
            out[r][c][1] = (unsigned char)go;
            out[r][c][2] = (unsigned char)bo;
        }
    }
}

// Push TB_FRAMES identical frames, run the kernel, drain and compare frame 3.
static int run_pass(const char* name, const Cfg& g) {
    static hls::stream<enh_pixel_t, 16384> s_in("s_in");
    static hls::stream<enh_pixel_t, 16384> s_out("s_out");

    build_golden(g, gold);

    for (int f = 0; f < TB_FRAMES; f++) {
        for (int y = 0; y < TB_H; y++) {
            for (int x = 0; x < TB_W; x++) {
                enh_pixel_t p;
                p.data = ((ap_uint<24>)rgb[y][x][0] << 16) |
                         ((ap_uint<24>)rgb[y][x][1] << 8) |
                         (ap_uint<24>)rgb[y][x][2];
                p.keep = (ap_uint<ENH_PIX_W / 8>)ENH_KEEP_ALL;
                p.strb = (ap_uint<ENH_PIX_W / 8>)ENH_KEEP_ALL;
                p.user = (f == 0 && y == 0 && x == 0) ? 1 : 0;
                p.last = (x == TB_W - 1) ? 1 : 0;
                p.id = 0;
                p.dest = 0;
                s_in.write(p);
            }
        }
    }

    enhance_stream(s_in, s_out,
                   (ap_uint<8>)g.clarity, (ap_uint<8>)g.knee,
                   (ap_uint<8>)g.glo, (ap_uint<8>)g.ghi,
                   (ap_uint<8>)g.thr, (ap_uint<1>)g.bin,
                   (ap_uint<1>)g.inv, (ap_uint<1>)g.mono,
                   (ap_uint<16>)g.split);

    int errors = 0;
    int beats = 0;
    for (int f = 0; f < TB_FRAMES; f++) {
        for (int y = 0; y < TB_H; y++) {
            for (int x = 0; x < TB_W; x++) {
                if (s_out.empty()) {
                    printf("FAIL[%s]: stream ran dry at frame %d row %d col %d\n", name, f, y, x);
                    return 1;
                }
                enh_pixel_t q = s_out.read();
                beats++;

                if (q.last != (ap_uint<1>)(x == TB_W - 1)) {
                    if (errors < 5) printf("FAIL[%s]: last wrong at f%d y%d x%d\n", name, f, y, x);
                    errors++;
                }
                if (q.keep != (ap_uint<ENH_PIX_W / 8>)ENH_KEEP_ALL ||
                    q.strb != (ap_uint<ENH_PIX_W / 8>)ENH_KEEP_ALL) {
                    if (errors < 5) printf("FAIL[%s]: keep/strb clobbered at f%d y%d x%d\n", name, f, y, x);
                    errors++;
                }

                if (f == TB_FRAMES - 1) {
                    got[y][x][0] = (unsigned char)q.data.range(23, 16);
                    got[y][x][1] = (unsigned char)q.data.range(15, 8);
                    got[y][x][2] = (unsigned char)q.data.range(7, 0);
                    for (int ch = 0; ch < 3; ch++) {
                        if (got[y][x][ch] != gold[y][x][ch]) {
                            if (errors < 12) {
                                printf("MISMATCH[%s] y=%2d x=%2d ch=%d got=%3u gold=%3u\n",
                                       name, y, x, ch, (unsigned)got[y][x][ch],
                                       (unsigned)gold[y][x][ch]);
                            }
                            errors++;
                        }
                    }
                }
            }
        }
    }

    if (!s_out.empty()) {
        printf("FAIL[%s]: kernel produced more beats than it consumed\n", name);
        errors++;
    }
    if (beats != TB_W * TB_H * TB_FRAMES) {
        printf("FAIL[%s]: beat count %d, expected %d\n", name, beats, TB_W * TB_H * TB_FRAMES);
        errors++;
    }
    printf("[%s] beats=%d errors=%d\n", name, beats, errors);
    return errors;
}

int main() {
    build_image();

    // A: local contrast boost, colour preserved, left half untouched (split).
    Cfg a;
    a.clarity = 24; a.knee = 255; a.glo = 16; a.ghi = 16;
    a.thr = 0; a.bin = 0; a.inv = 0; a.mono = 0; a.split = TB_W / 2;

    // B: identity clarity, shadow-lifting tone curve, binarise, invert, mono.
    Cfg b;
    b.clarity = 16; b.knee = 100; b.glo = 40; b.ghi = 12;
    b.thr = 128; b.bin = 1; b.inv = 1; b.mono = 1; b.split = 0;

    int errors = 0;
    errors += run_pass("A_clarity_split", a);
    errors += run_pass("B_tone_binarise", b);

    printf(errors == 0 ? "ENHANCE TB PASS\n" : "ENHANCE TB FAIL\n");
    return errors == 0 ? 0 : 1;
}
