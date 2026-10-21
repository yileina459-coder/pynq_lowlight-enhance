// -----------------------------------------------------------------------------
// enh_rst_gate - give the PS a way to reset the free-running kernel, safely.
//
// Why this exists
//   enhance_stream runs with ap_ctrl_none, so it never "starts": its pipeline prologue
//   executes once and HLS registers the loop-invariant configuration inputs there
//   (evidence in the generated netlist: `binarize_read_reg_1446 <= binarize;`). Six of
//   the nine parameters therefore freeze at the value present at power-up, so changing
//   them from the PS has no effect until the prologue runs again.
//
//   Re-running the prologue is enough to re-sample them, so the PS pulses this gate:
//
//       rst_n_async = aresetn & ~cfg_hi[31]
//
//   Bit 31 of the second GPIO channel is unused by enh_cfg_split (the packed
//   configuration is 59 bits: word1 only uses bits 26:0), so writing it cannot disturb
//   any parameter.
//
// Why the output is re-timed
//   cfg_hi comes from the 100 MHz PS clock domain while the kernel runs on
//   ap_clk (142.857 MHz). Driving ap_rst_n straight from that comparison releases the
//   kernel from reset on an arbitrary phase of its own clock, which can leave the
//   pipeline - notably the line-buffer write pointers - starting in a corrupted state.
//   On the board that showed up as one preset flickering continuously until the next
//   reset happened to land on a good phase.
//
//   So this is a standard asynchronous-assert / synchronous-de-assert reset bridge:
//   the request takes effect immediately, and the release is re-timed through two
//   flops in the kernel's own clock domain.
//
//   Cost of this approach: one frame of disturbed video per parameter change (the line
//   buffers are cleared). The clean alternative is to move the six frozen parameters
//   into a BRAM so that HLS cannot hoist the reads out of the loop.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module enh_rst_gate (
    input  wire        aclk,      // kernel clock (ap_clk)
    input  wire        aresetn,   // board-level reset, active low, PS domain
    input  wire [31:0] cfg_hi,    // second configuration word
    output wire        ap_rst_n   // to the kernel's ap_rst_n
);

    wire rst_n_async = aresetn & ~cfg_hi[31];

    // Async assert, sync de-assert. Two flops are enough for a reset bridge: the
    // first may go metastable, the second resolves it before it reaches the kernel.
    reg [1:0] sync;

    always @(posedge aclk or negedge rst_n_async) begin
        if (!rst_n_async) begin
            sync <= 2'b00;
        end else begin
            sync <= {sync[0], 1'b1};
        end
    end

    assign ap_rst_n = sync[1];

endmodule
