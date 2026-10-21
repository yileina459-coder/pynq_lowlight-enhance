// -----------------------------------------------------------------------------
// enh_rst_bridge - PS-controlled reset for the free-running kernel, with the release
// re-timed into the kernel's own clock domain.
//
// Why a new module name
//   The first version was called enh_rst_gate and had no clock port; its de-assertion was
//   driven straight from the 100 MHz PS-domain comparison. On the board that produced one
//   preset flickering continuously: the kernel came out of reset on an arbitrary phase of
//   its 142.857 MHz clock, which can leave the line-buffer pointers starting in a
//   corrupted state.
//
//   Editing the RTL and re-creating a block-design cell with the same module name does
//   not help - Vivado caches module references by name, so the cell still reports the old
//   port list ("the gate has no aclk pin"). Hence a new module name, which forces a fresh
//   definition.
//
// What it does
//       rst_n_async = aresetn & ~cfg_hi[31]        // async assert
//       ap_rst_n    = two-FF synchroniser output   // sync de-assert in aclk domain
//
//   cfg_hi[31] is free: enh_cfg_split only packs 59 bits and uses word1[26:0].
//   Cost: one frame of disturbed video per parameter change (line buffers are cleared).
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module enh_rst_bridge (
    input  wire        aclk,      // kernel clock (ap_clk)
    input  wire        aresetn,   // board-level reset, active low, PS domain
    input  wire [31:0] cfg_hi,    // second configuration word
    output wire        ap_rst_n   // to the kernel's ap_rst_n
);

    wire rst_n_async = aresetn & ~cfg_hi[31];

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
