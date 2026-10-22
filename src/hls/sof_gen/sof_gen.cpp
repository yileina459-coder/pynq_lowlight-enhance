// -----------------------------------------------------------------------------
// sof_gen.cpp - generate the frame-start marker (TUSER/SOF) the VDMA does not provide.
//
// Why this exists
//   v_axi4s_vid_out aligns each incoming frame to its own timing generator using SOF, which travels
//   on the AXI4-Stream TUSER line (Xilinx PG044: "the Start-Of-Frame signal, physically transmitted
//   over the AXI4-Stream TUSER0 signal, marks the first pixel of a video frame"). In this design
//   TUSER comes from the AXI VDMA's m_axis_mm2s_tuser, which is held low, so the output core
//   free-runs and the picture lands at whatever pixel phase start-up produced. Measured offsets
//   across three sessions with the same bitstream: about 0, 45 and 89 pixels.
//
// Why HLS and not a hand-written module
//   The first attempt was plain RTL with individual input/output pins, wired pin-by-pin into the
//   block design. That breaks the AXI4-Stream *interface* connection between pixel_unpack and
//   v_axi4s_vid_out, and PYNQ's metadata parser then refuses the overlay:
//
//       MetadataObjectNotFound: s_axis_video_tdata[port]:s_axis_video_tdata[signal] cannot be
//       found in base:video_hdmi_out_frontend_v_axi4s_vid_out_0[block]
//
//   An HLS kernel with #pragma HLS INTERFACE axis keeps the stream as an interface on both sides,
//   so the block design stays interface-to-interface and the .hwh remains parseable.
//
// What it does
//   Passes every beat through unchanged except TUSER, which is asserted on the first pixel of each
//   frame. The frame boundary is derived from the only structure the stream has - one TLAST per
//   line and a fixed line count - which is safe here because the VDMA emits back-to-back frames of
//   a single geometry.
//
// Latency
//   One pipeline stage for the data, II = 1. That is a single pixel clock and is included in the
//   measured pipeline latency; it does not affect frame alignment, which is what SOF fixes.
// -----------------------------------------------------------------------------
#include "hls_stream.h"
#include "ap_axi_sdata.h"
#include "ap_int.h"

#ifndef SOF_PIX_W
#define SOF_PIX_W 24
#endif

// Active lines per frame. 480 for the 640x480 output this board supports.
#ifndef SOF_LINES
#define SOF_LINES 480
#endif

typedef ap_axiu<SOF_PIX_W, 1, 1, 1> sof_pixel_t;
typedef hls::stream<sof_pixel_t> sof_stream_t;

void sof_gen(sof_stream_t& s_in, sof_stream_t& s_out) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE ap_ctrl_none port = return

    // 9 bits hold 0..479; declared and compared at the same width because a mismatch here once
    // produced [Opt 31-67] "LUT4 ... missing a connection on input pin I3" and cost a build.
    static ap_uint<9> line = 0;
    static ap_uint<1> sof = 1;      // the first pixel after reset starts a frame

#ifdef __SYNTHESIS__
    while (1) {
#else
    for (int _emu = 0; _emu < 307200; _emu++) {   // one 640x480 frame in C simulation
#endif
#pragma HLS PIPELINE II = 1

        sof_pixel_t pin = s_in.read();
        sof_pixel_t pout = pin;
        pout.user = sof;             // replace the VDMA's constant 0 with the generated marker

        ap_uint<1> last_line = (line == (ap_uint<9>)(SOF_LINES - 1)) ? ap_uint<1>(1)
                                                                    : ap_uint<1>(0);
        if (pin.last) {
            sof = last_line;
            line = last_line ? ap_uint<9>(0) : ap_uint<9>(line + 1);
        } else {
            sof = 0;
        }

        s_out.write(pout);
    }
}
