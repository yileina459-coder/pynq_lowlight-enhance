// -----------------------------------------------------------------------------
// tb_sharpen.cpp - C simulation testbench for sharpen_stream
//
// Independent software golden model of the same kernel and border policy, three
// frames pushed so the line buffer rotation is exercised across frame
// boundaries, third frame compared bit for bit.
// -----------------------------------------------------------------------------
#include "sharpen.hpp"

#include <cstdio>

#define TB_W 64
#define TB_H 48
#define TB_FRAMES 3

static unsigned char rgb[TB_H][TB_W][3];
static unsigned char gold[TB_H][TB_W][3];

static unsigned char sharp_px(int r, int c, int ch) {
    int r0 = (r - 2 + TB_H) % TB_H;
    int r1 = (r - 1 + TB_H) % TB_H;
    int r2 = r;
    int c0 = (c - 2 < 0) ? 0 : c - 2;
    int c1 = (c - 1 < 0) ? 0 : c - 1;
    int c2 = c;

    int centre = rgb[r1][c1][ch];
    int up = rgb[r0][c1][ch];
    int down = rgb[r2][c1][ch];
    int left = rgb[r1][c0][ch];
    int right = rgb[r1][c2][ch];

    int acc = 5 * centre - up - down - left - right;
    if (acc < 0) return 0;
    if (acc > 255) return 255;
    return (unsigned char)acc;
}

static void build_image() {
    for (int y = 0; y < TB_H; y++) {
        for (int x = 0; x < TB_W; x++) {
            unsigned r, g, b;
            if (x >= 16 && x < 40 && y >= 12 && y < 30) {
                r = 230; g = 230; b = 230;
            } else if (((x >> 2) + (y >> 2)) & 1) {
                r = (unsigned)((x * 4) & 0xff);
                g = (unsigned)((y * 5) & 0xff);
                b = (unsigned)((x * y) & 0xff);
            } else {
                r = (unsigned)((x * 2 + y) & 0xff);
                g = (unsigned)((y * 3) & 0xff);
                b = (unsigned)((x ^ y) & 0xff);
            }
            rgb[y][x][0] = (unsigned char)r;
            rgb[y][x][1] = (unsigned char)g;
            rgb[y][x][2] = (unsigned char)b;
        }
    }
    for (int y = 0; y < TB_H; y++) {
        for (int x = 0; x < TB_W; x++) {
            for (int ch = 0; ch < 3; ch++) {
                gold[y][x][ch] = sharp_px(y, x, ch);
            }
        }
    }
}

int main() {
    static hls::stream<sharp_pixel_t, 16384> s_in("s_in");
    static hls::stream<sharp_pixel_t, 16384> s_out("s_out");

    build_image();

    for (int f = 0; f < TB_FRAMES; f++) {
        for (int y = 0; y < TB_H; y++) {
            for (int x = 0; x < TB_W; x++) {
                sharp_pixel_t p;
                p.data = ((ap_uint<24>)rgb[y][x][0] << 16) |
                         ((ap_uint<24>)rgb[y][x][1] << 8) |
                         (ap_uint<24>)rgb[y][x][2];
                p.keep = (ap_uint<SHARP_PIX_W / 8>)SHARP_KEEP_ALL;
                p.strb = (ap_uint<SHARP_PIX_W / 8>)SHARP_KEEP_ALL;
                p.user = 0;
                p.last = (x == TB_W - 1) ? 1 : 0;
                p.id = 0;
                p.dest = 0;
                s_in.write(p);
            }
        }
    }

    sharpen_stream(s_in, s_out);

    int errors = 0;
    int beats = 0;
    int clamped_low = 0;
    int clamped_high = 0;

    for (int f = 0; f < TB_FRAMES; f++) {
        for (int y = 0; y < TB_H; y++) {
            for (int x = 0; x < TB_W; x++) {
                if (s_out.empty()) {
                    printf("FAIL: stream ran dry at f%d y%d x%d\n", f, y, x);
                    return 1;
                }
                sharp_pixel_t q = s_out.read();
                beats++;

                if (f == TB_FRAMES - 1) {
                    unsigned r = q.data.range(23, 16);
                    unsigned g = q.data.range(15, 8);
                    unsigned b = q.data.range(7, 0);
                    if (r != gold[y][x][0] || g != gold[y][x][1] || b != gold[y][x][2]) {
                        if (errors < 5) {
                            printf("MISMATCH y=%2d x=%2d got=(%u,%u,%u) gold=(%u,%u,%u)\n",
                                   y, x, r, g, b, gold[y][x][0], gold[y][x][1], gold[y][x][2]);
                        }
                        errors++;
                    }
                    if (gold[y][x][0] == 0 || gold[y][x][1] == 0 || gold[y][x][2] == 0) {
                        clamped_low++;
                    }
                    if (gold[y][x][0] == 255 || gold[y][x][1] == 255 || gold[y][x][2] == 255) {
                        clamped_high++;
                    }
                }
            }
        }
    }

    if (!s_out.empty()) {
        printf("FAIL: more output beats than input\n");
        errors++;
    }

    // If nothing clamps, the test image never exercises the saturation path and
    // the comparison is weaker than it looks.
    printf("clamped-low pixels: %d, clamped-high pixels: %d\n", clamped_low, clamped_high);
    if (clamped_low == 0 && clamped_high == 0) {
        printf("WARNING: test image never exercised clamping\n");
    }

    printf("beats=%d expected=%d\n", beats, TB_W * TB_H * TB_FRAMES);
    printf(errors == 0 ? "SHARPEN TB PASS\n" : "SHARPEN TB FAIL\n");
    return errors == 0 ? 0 : 1;
}
