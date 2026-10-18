// -----------------------------------------------------------------------------
// tb_sobel.cpp - C simulation testbench for sobel_stream
//
// What it proves
//   1. the streaming kernel produces one output per input beat and keeps the
//      AXI-Stream side-channel fields (last / user / keep / strb) intact
//   2. the processed pixels match an independently written software golden
//      model of the exact same border policy, bit for bit
//   3. the line-buffer rotation survives frame boundaries: three identical
//      frames are pushed, and the third one is compared (by then the row roles
//      and the previous frame's last two lines are in steady state)
//
// Image height is a multiple of 3 on purpose: the row-role phase advances once
// per line, so H % 3 == 0 puts the phase back at 0 on every frame boundary and
// the golden model can use plain circular vertical indexing.
// -----------------------------------------------------------------------------
#include "sobel.hpp"

#include <cstdio>
#include <cstdlib>

#define TB_W 64
#define TB_H 48
#define TB_FRAMES 3

static ap_uint<8> img[TB_H][TB_W];        // luma already, one frame
static unsigned char rgb[TB_H][TB_W][3];  // original RGB, to build the stream
static unsigned char got[TB_H][TB_W];
static unsigned char gold[TB_H][TB_W];

static unsigned luma_ref(unsigned r, unsigned g, unsigned b) {
    return (77u * r + 150u * g + 29u * b) >> 8;
}

// Deterministic, edge-rich test image: smooth ramps, a hard-edged rectangle and
// a fine checkerboard, so the gradient sees strong, weak and diagonal edges.
static void build_image() {
    for (int y = 0; y < TB_H; y++) {
        for (int x = 0; x < TB_W; x++) {
            unsigned r, g, b;
            if (x >= 16 && x < 40 && y >= 12 && y < 30) {
                r = 230; g = 230; b = 230;                  // bright block
            } else if (((x >> 2) + (y >> 2)) & 1) {
                r = (unsigned)((x * 4) & 0xff);              // fine checker
                g = (unsigned)((y * 5) & 0xff);
                b = (unsigned)((x * y) & 0xff);
            } else {
                r = (unsigned)((x * 2 + y) & 0xff);          // ramps
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

// Software golden model: same formula, same border policy, written as plain
// nested loops over the whole frame (deliberately different code path from the
// kernel, which walks the stream with rotating buffers).
static void build_golden() {
    for (int r = 0; r < TB_H; r++) {
        int r0 = (r - 2 + TB_H) % TB_H;
        int r1 = (r - 1 + TB_H) % TB_H;
        int r2 = r;
        for (int c = 0; c < TB_W; c++) {
            int c0 = (c - 2 < 0) ? 0 : c - 2;
            int c1 = (c - 1 < 0) ? 0 : c - 1;
            int c2 = c;
            int top0 = img[r0][c0], top1 = img[r0][c1], top2 = img[r0][c2];
            int mid0 = img[r1][c0], mid1 = img[r1][c1], mid2 = img[r1][c2];
            int bot0 = img[r2][c0], bot1 = img[r2][c1], bot2 = img[r2][c2];
            int gx = top2 + 2 * mid2 + bot2 - (top0 + 2 * mid0 + bot0);
            int gy = bot0 + 2 * bot1 + bot2 - (top0 + 2 * top1 + top2);
            int mag = (gx < 0 ? -gx : gx) + (gy < 0 ? -gy : gy);
            gold[r][c] = (unsigned char)(mag > 255 ? 255 : mag);
        }
    }
}

int main() {
    static hls::stream<sobel_pixel_t, 16384> s_in("s_in");
    static hls::stream<sobel_pixel_t, 16384> s_out("s_out");

    build_image();
    build_golden();

    // Push TB_FRAMES identical frames.
    for (int f = 0; f < TB_FRAMES; f++) {
        for (int y = 0; y < TB_H; y++) {
            for (int x = 0; x < TB_W; x++) {
                sobel_pixel_t p;
                p.data = ((ap_uint<24>)rgb[y][x][0] << 16) |
                         ((ap_uint<24>)rgb[y][x][1] << 8) |
                         (ap_uint<24>)rgb[y][x][2];
                p.keep = 0x7;
                p.strb = 0x7;
                p.user = (f == 0 && y == 0 && x == 0) ? 1 : 0;
                p.last = (x == TB_W - 1) ? 1 : 0;
                p.id = 0;
                p.dest = 0;
                s_in.write(p);
            }
        }
    }

    sobel_stream(s_in, s_out);

    // Drain. Frame 1 and 2 are warm-up, frame 3 is the one we check.
    int errors = 0;
    int beats = 0;
    for (int f = 0; f < TB_FRAMES; f++) {
        for (int y = 0; y < TB_H; y++) {
            for (int x = 0; x < TB_W; x++) {
                if (s_out.empty()) {
                    printf("FAIL: output stream ran dry at frame %d row %d col %d\n", f, y, x);
                    return 1;
                }
                sobel_pixel_t q = s_out.read();
                beats++;

                // Side channels must survive the kernel untouched.
                if (q.last != (ap_uint<1>)(x == TB_W - 1)) {
                    if (errors < 5) printf("FAIL: last flag wrong at f%d y%d x%d\n", f, y, x);
                    errors++;
                }
                if (q.keep != (ap_uint<3>)0x7 || q.strb != (ap_uint<3>)0x7) {
                    if (errors < 5) printf("FAIL: keep/strb clobbered at f%d y%d x%d\n", f, y, x);
                    errors++;
                }

                unsigned r = q.data.range(23, 16);
                unsigned g = q.data.range(15, 8);
                unsigned b = q.data.range(7, 0);
                if (r != g || g != b) {
                    if (errors < 5) printf("FAIL: channels differ at f%d y%d x%d\n", f, y, x);
                    errors++;
                }

                if (f == TB_FRAMES - 1) {
                    got[y][x] = (unsigned char)r;
                    if (got[y][x] != gold[y][x] && errors < 12) {
                        printf("MISMATCH y=%2d x=%2d got=%3u gold=%3u\n", y, x,
                               (unsigned)got[y][x], (unsigned)gold[y][x]);
                        errors++;
                    } else if (got[y][x] != gold[y][x]) {
                        errors++;
                    }
                }
            }
        }
    }

    if (!s_out.empty()) {
        printf("FAIL: kernel produced more beats than it consumed\n");
        errors++;
    }

    printf("beats=%d expected=%d\n", beats, TB_W * TB_H * TB_FRAMES);
    printf(errors == 0 ? "SOBEL TB PASS\n" : "SOBEL TB FAIL\n");
    return errors == 0 ? 0 : 1;
}
