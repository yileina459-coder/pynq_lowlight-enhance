// -----------------------------------------------------------------------------
// enh_rst_gate - give the PS a way to reset the free-running kernel.
//
// Why this exists
//   enhance_stream runs with ap_ctrl_none, so it never "starts": its pipeline
//   prologue executes once and HLS registers the loop-invariant configuration inputs
//   there (evidence in the generated netlist: `binarize_read_reg_1446 <= binarize;`).
//   Six of the nine parameters therefore freeze at the value present at power-up, and
//   changing them from the PS has no effect - knee, thresh, binarize, invert, mono and
//   split_x were all stuck, while clarity, gain_lo and gain_hi stayed live because HLS
//   happened to keep them combinational.
//
//   Re-running the prologue is enough to re-sample them, so this gate lets the PS
//   pulse the kernel's reset:
//
//       ap_rst_n = board_aresetn & ~cfg_hi[31]
//
//   Bit 31 of the second GPIO channel is unused by enh_cfg_split (the packed
//   configuration is 59 bits: word1 only uses bits 26:0), so writing it cannot disturb
//   any parameter. Default after configuration is 0, i.e. reset released.
//
//   The cost of this approach is one frame of disturbed video per parameter change; the
//   clean alternative is to move those parameters into a BRAM so HLS cannot hoist the
//   reads out of the loop.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module enh_rst_gate (
    input  wire        aresetn,   // board-level reset, active low
    input  wire [31:0] cfg_hi,    // second configuration word
    output wire        ap_rst_n   // to the kernel's ap_rst_n
);

    assign ap_rst_n = aresetn & ~cfg_hi[31];

endmodule
