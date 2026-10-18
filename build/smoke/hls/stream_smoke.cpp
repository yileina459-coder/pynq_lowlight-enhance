#include <hls_stream.h>
#include <ap_axi_sdata.h>

typedef ap_axiu<24, 1, 1, 1> pixel_t;

// Minimal AXI-Stream pass-through with per-pixel invert, used only to validate
// the Vitis HLS 2026.1 flow (C sim -> C synth -> export IP).
void stream_smoke(hls::stream<pixel_t>& s_in, hls::stream<pixel_t>& s_out) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE ap_ctrl_none port = return
loop_pixel:
    for (int i = 0; i < 16; i++) {
#pragma HLS PIPELINE II = 1
        pixel_t p = s_in.read();
        ap_uint<24> d = p.data;
        p.data = (ap_uint<24>)~d;
        s_out.write(p);
    }
}
