// -----------------------------------------------------------------------------
// axis_sof_gen - assert TUSER on the first pixel of every frame.
//
// Why this exists
//   v_axi4s_vid_out aligns the incoming frame to its own timing generator using SOF, which is
//   carried on TUSER (Xilinx PG044: "the Start-Of-Frame signal, physically transmitted over the
//   AXI4-Stream TUSER0 signal, marks the first pixel of a video frame"). In this design TUSER
//   comes from the AXI VDMA, and the VDMA drives m_axis_mm2s_tuser constantly low. With no SOF
//   the core is free-running: the picture lands at whatever pixel phase the moment of start-up
//   happened to produce, so the horizontal offset changes from one session to the next - which is
//   exactly what was measured (about 0 px, then 45 px, then 89 px for the same bitstream).
//
//   This module manufactures the missing SOF from the only frame structure the stream has: one
//   TLAST per line and a fixed number of lines. That is reliable here because the VDMA emits
//   back-to-back frames of a single, fixed geometry.
//
// Latency
//   Purely combinational on the data path: tdata/tvalid/tlast/tready pass straight through and
//   only tuser is overridden. Inserting it therefore does not change the measured pipeline
//   latency or any timing closure.
//
// Reset behaviour
//   tuser is asserted on the first pixel after reset so the very first frame is aligned too.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module axis_sof_gen #(
    parameter integer LINES     = 480,   // active lines per frame
    parameter integer DATA_W    = 24     // AXI4-Stream data width at this point
) (
    input  wire                aclk,
    input  wire                aresetn,

    // slave side (from pixel_unpack)
    input  wire [DATA_W-1:0]   s_tdata,
    input  wire                s_tvalid,
    output wire                s_tready,
    input  wire                s_tlast,
    input  wire                s_tuser,

    // Runtime switch, driven from a spare configuration GPIO bit.
    //   1 = override tuser with the generated SOF
    //   0 = pass tuser through (behaves exactly like the design without this module)
    // Having both behaviours in one bitstream means a comparison costs a register write instead
    // of a 35-minute rebuild, which matters because the SOF assertion point is exactly the thing
    // being determined.
    input  wire                sof_enable,

    // master side (to v_axi4s_vid_out)
    output wire [DATA_W-1:0]   m_tdata,
    output wire                m_tvalid,
    input  wire                m_tready,
    output wire                m_tlast,
    output wire                m_tuser
);

    // The counter width and the "last line" constant are declared with matching widths on
    // purpose. Comparing a 9-bit counter against an untyped 32-bit parameter (LINES - 1) made
    // opt_design fail with [Opt 31-67]: "A LUT4 cell in the design is missing a connection on
    // input pin I3 ... LUT cell name is base_i/sof_gen_0/inst/sof_i_4". Keeping both sides the
    // same width avoids that elaboration.
    localparam integer LINE_BITS = 9;                       // 480 lines fit in 9 bits
    localparam [LINE_BITS-1:0] LAST_LINE = LINES - 1;

    reg [LINE_BITS-1:0] line = {LINE_BITS{1'b0}};
    reg                 sof  = 1'b1;

    assign m_tdata  = s_tdata;
    assign m_tvalid = s_tvalid;
    assign m_tlast  = s_tlast;
    assign s_tready = m_tready;
    assign m_tuser  = sof_enable ? sof : s_tuser;

    wire beat = s_tvalid & m_tready;

    always @(posedge aclk) begin
        if (!aresetn) begin
            line <= {LINE_BITS{1'b0}};
            sof  <= 1'b1;
        end else if (beat) begin
            sof <= 1'b0;                // only the first pixel of a frame carries it
            if (s_tlast) begin
                if (line == LAST_LINE) begin
                    line <= {LINE_BITS{1'b0}};
                    sof  <= 1'b1;       // next pixel starts a new frame
                end else begin
                    line <= line + 1'b1;
                end
            end
        end
    end

endmodule
