// -----------------------------------------------------------------------------
// axis_tlast_gen - regenerate TLAST every WIDTH beats.
//
// Why this exists
//   The AXI DMA needs TLAST to close a transfer. On the board, the transfer
//   through the HLS kernel never completed: 16 words (one AXI burst) stayed in
//   the DMA's buffer every time, which is the signature of a missing TLAST (see
//   board/dma_sobel/diag_dma*.py for the measurements). Instead of trusting the
//   marker that comes out of the kernel, this cell counts beats and asserts
//   TLAST itself, so a transfer of exactly WIDTH beats always closes.
//
// Behaviour
//   Data and handshake pass through unchanged (no added latency). The incoming
//   TLAST is ignored and replaced. WIDTH must be >= 1; the counter is 16 bits,
//   so up to 65535 beats - set WIDTH to the frame size for whole-frame transfers.
//
// Port names follow the AXI4-Stream convention on purpose: Vivado's module
// reference can then infer the interface when the cell is dropped into a block
// design, with no IP packaging step.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module axis_tlast_gen #(
    parameter integer WIDTH  = 1280,
    parameter integer DATA_W = 32,
    parameter integer USER_W = 1,
    parameter integer ID_W   = 1,
    parameter integer DEST_W = 1
) (
    input  wire              aclk,
    input  wire              aresetn,

    input  wire [DATA_W-1:0] s_axis_tdata,
    input  wire              s_axis_tvalid,
    output wire              s_axis_tready,
    input  wire [DATA_W/8-1:0] s_axis_tkeep,
    input  wire [DATA_W/8-1:0] s_axis_tstrb,
    input  wire [USER_W-1:0] s_axis_tuser,
    input  wire [ID_W-1:0]   s_axis_tid,
    input  wire [DEST_W-1:0] s_axis_tdest,
    input  wire              s_axis_tlast,   // accepted but not forwarded

    output wire [DATA_W-1:0] m_axis_tdata,
    output wire              m_axis_tvalid,
    input  wire              m_axis_tready,
    output wire [DATA_W/8-1:0] m_axis_tkeep,
    output wire [DATA_W/8-1:0] m_axis_tstrb,
    output wire [USER_W-1:0] m_axis_tuser,
    output wire [ID_W-1:0]   m_axis_tid,
    output wire [DEST_W-1:0] m_axis_tdest,
    output wire              m_axis_tlast
);

    localparam integer LAST_INDEX = WIDTH - 1;

    reg [15:0] beat_count;

    assign m_axis_tdata  = s_axis_tdata;
    assign m_axis_tkeep  = s_axis_tkeep;
    assign m_axis_tstrb  = s_axis_tstrb;
    assign m_axis_tuser  = s_axis_tuser;
    assign m_axis_tid    = s_axis_tid;
    assign m_axis_tdest  = s_axis_tdest;
    assign m_axis_tvalid = s_axis_tvalid;
    assign s_axis_tready = m_axis_tready;

    // Combinational on the beat being presented, so TLAST rides the last pixel.
    assign m_axis_tlast = (beat_count == LAST_INDEX);

    always @(posedge aclk) begin
        if (!aresetn) begin
            beat_count <= 16'd0;
        end else if (s_axis_tvalid && m_axis_tready) begin
            if (beat_count == LAST_INDEX) begin
                beat_count <= 16'd0;
            end else begin
                beat_count <= beat_count + 16'd1;
            end
        end
    end

    // TLAST in is deliberately unused; the port stays so the cell can replace a
    // direct connection without rewiring the incoming interface.
    wire unused_tlast = s_axis_tlast;

endmodule
