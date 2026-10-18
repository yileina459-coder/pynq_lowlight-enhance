// -----------------------------------------------------------------------------
// axis_mux3 - pick one of three AXI4-Stream sources, drain the other two.
//
// Why "drain" and not "pause"
//   The intended use is three operators running on the same input stream, all in
//   lockstep (each produces exactly one beat per input beat). Pausing the
//   unselected operators with TREADY=0 would back-pressure the broadcast feeding
//   all three, which would stall the selected one too. So the unselected inputs
//   are accepted and dropped: every operator keeps running, and the display just
//   shows whichever one is selected.
//
// Interface
//   Only TDATA / TVALID / TREADY / TLAST are carried. That is enough for the
//   pixel stream between PYNQ's pixel_pack and pixel_unpack, and it keeps the
//   cell small enough to drop into a block design without touching timing
//   closure of the surrounding video path.
//
// Latency
//   Combinational selection: zero added latency, one beat per beat.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module axis_mux3 #(
    parameter integer DATA_W = 32
) (
    input  wire              aclk,
    input  wire              aresetn,
    input  wire [1:0]        sel,      // 0,1,2 select; 3 is undefined -> input 0

    // inputs
    input  wire [DATA_W-1:0] s0_tdata,
    input  wire              s0_tvalid,
    output wire              s0_tready,
    input  wire              s0_tlast,

    input  wire [DATA_W-1:0] s1_tdata,
    input  wire              s1_tvalid,
    output wire              s1_tready,
    input  wire              s1_tlast,

    input  wire [DATA_W-1:0] s2_tdata,
    input  wire              s2_tvalid,
    output wire              s2_tready,
    input  wire              s2_tlast,

    // output
    output reg  [DATA_W-1:0] m_tdata,
    output reg               m_tvalid,
    input  wire              m_tready,
    output reg               m_tlast
);

    wire [1:0] sel_safe = (sel == 2'd3) ? 2'd0 : sel;

    // Unselected inputs are always drained.
    // The selected input only accepts when the downstream is ready.
    assign s0_tready = (sel_safe == 2'd0) ? m_tready : 1'b1;
    assign s1_tready = (sel_safe == 2'd1) ? m_tready : 1'b1;
    assign s2_tready = (sel_safe == 2'd2) ? m_tready : 1'b1;

    always @(*) begin
        case (sel_safe)
            2'd1: begin
                m_tdata  = s1_tdata;
                m_tvalid = s1_tvalid;
                m_tlast  = s1_tlast;
            end
            2'd2: begin
                m_tdata  = s2_tdata;
                m_tvalid = s2_tvalid;
                m_tlast  = s2_tlast;
            end
            default: begin
                m_tdata  = s0_tdata;
                m_tvalid = s0_tvalid;
                m_tlast  = s0_tlast;
            end
        endcase
    end

    // aresetn is unused: this cell is purely combinational and introduces no
    // state that could need resetting. Kept in the port list so the block design
    // automation can connect it like any other stream cell.
    wire unused = aresetn & aclk;
endmodule
