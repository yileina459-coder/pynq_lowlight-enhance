#include <hls_stream.h>
#include <ap_axi_sdata.h>
#include <cstdio>

typedef ap_axiu<24, 1, 1, 1> pixel_t;
void stream_smoke(hls::stream<pixel_t>& s_in, hls::stream<pixel_t>& s_out);

int main() {
    hls::stream<pixel_t> in, out;
    const int N = 16;
    for (int i = 0; i < N; i++) {
        pixel_t p;
        p.data = (ap_uint<24>)(0x123456 + i);
        p.keep = 0x7;
        p.strb = 0x7;
        p.user = 0;
        p.last = (i == N - 1) ? 1 : 0;
        in.write(p);
    }
    stream_smoke(in, out);

    int err = 0;
    for (int i = 0; i < N; i++) {
        pixel_t p = out.read();
        ap_uint<24> exp = (ap_uint<24>)~(ap_uint<24>)(0x123456 + i);
        if (p.data != exp) {
            printf("MISMATCH i=%d got=%06x exp=%06x\n", i, (unsigned)p.data, (unsigned)exp);
            err++;
        }
    }
    printf(err == 0 ? "SMOKE PASS\n" : "SMOKE FAIL\n");
    return err;
}
