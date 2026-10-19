// -----------------------------------------------------------------------------
// enh_cfg_split - turn two 32-bit AXI GPIO channels into the 59 config bits.
//
// Why this exists
//   enhance_stream takes its configuration as ten separate ports (8+8+8+8+8+1+1+1+16
//   = 59 bits). A block design cannot slice a 64-bit GPIO output into those ports
//   without glue, and adding AXI-Lite to the kernel would mean rebuilding it just
//   to move registers around. Two axi_gpio channels plus this cell are cheaper,
//   and the PS can still change any parameter while the video keeps running.
//
// Bit layout (word 0 = gpio channel 1, word 1 = gpio channel 2)
//   word0[ 7: 0] clarity      word1[ 7: 0] thresh
//   word0[15: 8] knee         word1[ 8]    binarize
//   word0[23:16] gain_lo      word1[ 9]    invert
//   word0[31:24] gain_hi      word1[10]    mono
//                             word1[26:11] split_x
//
// Unused upper bits of word1 are ignored, so a stray write cannot upset anything.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module enh_cfg_split (
    input  wire [31:0] cfg_lo,
    input  wire [31:0] cfg_hi,

    output wire [7:0]  clarity,
    output wire [7:0]  knee,
    output wire [7:0]  gain_lo,
    output wire [7:0]  gain_hi,
    output wire [7:0]  thresh,
    output wire        binarize,
    output wire        invert,
    output wire        mono,
    output wire [15:0] split_x
);

    assign clarity  = cfg_lo[7:0];
    assign knee     = cfg_lo[15:8];
    assign gain_lo  = cfg_lo[23:16];
    assign gain_hi  = cfg_lo[31:24];

    assign thresh   = cfg_hi[7:0];
    assign binarize = cfg_hi[8];
    assign invert   = cfg_hi[9];
    assign mono     = cfg_hi[10];
    assign split_x  = cfg_hi[26:11];

endmodule
