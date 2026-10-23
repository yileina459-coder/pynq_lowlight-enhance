// -----------------------------------------------------------------------------
// enhance.cpp - streaming image enhancer, one pixel per clock (II=1)
//
// Structure is deliberately the same as sobel.cpp: three rotating line buffers
// plus a 3-tap shift register per row. Each line buffer is read once and written
// once per pixel, which is what keeps II=1 inside the capability of a single
// true dual-port BRAM.
//
// The difference is the arithmetic: instead of a gradient it builds a local mean
// (1-2-1 Gaussian, i.e. the same 3x3 window) and uses it as the reference for a
// local contrast boost, then a two-segment tone curve, then optional
// binarisation / inversion, then a per-channel colour shift.
//
// Everything is integer and saturating. The C++ golden model in tb_enhance.cpp
// and sim/enhance/golden_enhance.py implement the same steps in a different code
// path, so a mismatch means the hardware is wrong, not that the model is.
// -----------------------------------------------------------------------------
#include "enhance.hpp"

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
                    ap_uint<16> split_x) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE ap_ctrl_none port = return

    // Uncomment (and delete ap_ctrl_none above) once the design goes into the
    // block design as a configurable core:
    //
    // #pragma HLS INTERFACE s_axilite port = clarity  bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = knee     bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = gain_lo  bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = gain_hi  bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = thresh   bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = binarize bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = invert   bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = mono     bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = split_x  bundle = ctrl
    // #pragma HLS INTERFACE s_axilite port = return   bundle = ctrl

    // Line buffers: [row role][column], complete partition on the row role turns
    // the three rows into three independent memories.
    static ap_uint<8> lbuf[3][ENH_MAX_W];
#pragma HLS ARRAY_PARTITION variable = lbuf complete dim = 1

    static ap_uint<8> wtop[3];
    static ap_uint<8> wmid[3];
    static ap_uint<8> wbot[3];
#pragma HLS ARRAY_PARTITION variable = wtop complete
#pragma HLS ARRAY_PARTITION variable = wmid complete
#pragma HLS ARRAY_PARTITION variable = wbot complete

    static ap_uint<12> col = 0;
    static ap_uint<2> phase = 0;

#ifdef __SYNTHESIS__
    while (1) {
#else
    for (int _emu = 0; _emu < ENH_EMU_PIXELS; _emu++) {
#endif
#pragma HLS PIPELINE II = 1

        #include "enhance_body.inc"
    }
}


// -----------------------------------------------------------------------------
// enhance_stream_cfg - the same pipeline, with the configuration in memory.
//
// Why
//   With the nine values on plain input ports, HLS registers them once in the pipeline
//   prologue (see binarize_read_reg_* in the generated netlist). A free-running kernel
//   only runs that prologue once, so changing a preset required resetting the kernel -
//   which interrupts the pixel stream and makes the video-output core underflow.
//
//   Reading the configuration from a memory port instead keeps the value live: HLS cannot
//   hoist a memory read out of the loop, because it cannot prove the contents do not
//   change. One 64-bit word holds all 59 configuration bits, so the loop issues a single
//   read per pixel and still keeps II = 1.
//
// Word layout (matches src/rtl/enh_cfg_split/enh_cfg_split.v)
//   [ 7: 0] clarity   [15: 8] knee    [23:16] gain_lo  [31:24] gain_hi
//   [39:32] thresh    [40] binarize  [41] invert       [42] mono
//   [58:43] split_x
// -----------------------------------------------------------------------------
void enhance_stream_cfg(enh_stream_t& s_in,
                        enh_stream_t& s_out,
                        ap_uint<64> cfg[2]) {
#pragma HLS INTERFACE axis port = s_in
#pragma HLS INTERFACE axis port = s_out
#pragma HLS INTERFACE bram port = cfg
#pragma HLS INTERFACE ap_ctrl_none port = return

    static ap_uint<8> lbuf[3][ENH_MAX_W];
#pragma HLS ARRAY_PARTITION variable = lbuf complete dim = 1

    static ap_uint<8> wtop[3];
    static ap_uint<8> wmid[3];
    static ap_uint<8> wbot[3];
#pragma HLS ARRAY_PARTITION variable = wtop complete
#pragma HLS ARRAY_PARTITION variable = wmid complete
#pragma HLS ARRAY_PARTITION variable = wbot complete

    static ap_uint<12> col = 0;
    static ap_uint<2> phase = 0;

#ifdef __SYNTHESIS__
    while (1) {
#else
    for (int _emu = 0; _emu < ENH_EMU_PIXELS; _emu++) {
#endif
#pragma HLS PIPELINE II = 1

        // Live configuration: re-read from memory for every pixel.
        //
        // The address is data-dependent on purpose. With a constant index HLS folds the
        // one-element array into a plain input port and then registers the one-bit flags in
        // the prologue - the exact latch this variant exists to avoid. A runtime address
        // forces a real memory port, so the word is re-read every cycle and cannot be held
        // in a register. Word 1 is never selected in practice.
        ap_uint<1> cfg_index = (col == (ap_uint<12>)0xFFF) ? ap_uint<1>(1) : ap_uint<1>(0);
        ap_uint<64> word = cfg[cfg_index];
        ap_uint<8> clarity  = word.range(7, 0);
        ap_uint<8> knee     = word.range(15, 8);
        ap_uint<8> gain_lo  = word.range(23, 16);
        ap_uint<8> gain_hi  = word.range(31, 24);
        ap_uint<8> thresh   = word.range(39, 32);
        ap_uint<1> binarize = word.range(40, 40);
        ap_uint<1> invert   = word.range(41, 41);
        ap_uint<1> mono     = word.range(42, 42);
        ap_uint<16> split_x = word.range(58, 43);

        #include "enhance_body.inc"
    }
}
