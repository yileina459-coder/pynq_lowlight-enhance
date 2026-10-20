// -----------------------------------------------------------------------------
// axis_cycle_stamp - stamps the cycle counter when the first beat passes.
//
// Why this exists
//   "Latency is about one line, not one frame" is the central claim of this
//   project and until now it was only an architectural argument. Two instances of
//   this cell, one before and one after the kernel, turn it into a measurement:
//
//       latency_cycles = t_out - t_in
//       latency_us     = latency_cycles / clock_hz * 1e6
//
//   Both instances share a clock and a reset, so their free-running counters are
//   identical; subtracting the two stamps is therefore well defined.
//
// Why two instances and not one
//   A single pass-through cell cannot see kernel latency: its own input and output
//   fire in the same cycle (m_axis_tvalid = s_axis_tvalid and
//   s_axis_tready = m_axis_tready), so both stamps land on the same value and the
//   latency always reads 0. That is exactly what the first version of this cell
//   did on the board - it was measuring its own wiring, not the kernel.
//
//   Sticky latches (rather than a live counter) are what make the value readable
//   from a slow PS over AXI-Lite without a fast polling loop. Re-loading the
//   overlay resets the PL and re-arms the measurement.
//
// The stream path is combinational, so the cell adds no latency of its own.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module axis_cycle_stamp #(
    parameter integer DATA_W = 32,
    parameter integer USER_W = 1,
    parameter integer ID_W   = 1,
    parameter integer DEST_W = 1
) (
    input  wire                aclk,
    input  wire                aresetn,

    input  wire [DATA_W-1:0]   s_axis_tdata,
    input  wire                s_axis_tvalid,
    output wire                s_axis_tready,
    input  wire [DATA_W/8-1:0] s_axis_tkeep,
    input  wire [DATA_W/8-1:0] s_axis_tstrb,
    input  wire [USER_W-1:0]   s_axis_tuser,
    input  wire [ID_W-1:0]     s_axis_tid,
    input  wire [DEST_W-1:0]   s_axis_tdest,
    input  wire                s_axis_tlast,

    output wire [DATA_W-1:0]   m_axis_tdata,
    output wire                m_axis_tvalid,
    input  wire                m_axis_tready,
    output wire [DATA_W/8-1:0] m_axis_tkeep,
    output wire [DATA_W/8-1:0] m_axis_tstrb,
    output wire [USER_W-1:0]   m_axis_tuser,
    output wire [ID_W-1:0]     m_axis_tid,
    output wire [DEST_W-1:0]   m_axis_tdest,
    output wire                m_axis_tlast,

    output wire [31:0]         first_cycle,
    output wire                first_seen,
    output wire [31:0]         beats
);

    assign m_axis_tdata  = s_axis_tdata;
    assign m_axis_tkeep  = s_axis_tkeep;
    assign m_axis_tstrb  = s_axis_tstrb;
    assign m_axis_tuser  = s_axis_tuser;
    assign m_axis_tid    = s_axis_tid;
    assign m_axis_tdest  = s_axis_tdest;
    assign m_axis_tlast  = s_axis_tlast;
    assign m_axis_tvalid = s_axis_tvalid;
    assign s_axis_tready = m_axis_tready;

    wire fire = s_axis_tvalid && s_axis_tready;

    reg [31:0] cyc;
    reg [31:0] stamp;
    reg        seen;

    always @(posedge aclk) begin
        if (!aresetn) cyc <= 32'd0;
        else          cyc <= cyc + 32'd1;
    end

    // first_cycle is latched once, so it cannot tell a running pipeline from one
    // that stalled after a few beats. `beats` can: read it twice a second apart.
    reg [31:0] count;

    always @(posedge aclk) begin
        if (!aresetn) begin
            stamp <= 32'd0;
            seen  <= 1'b0;
            count <= 32'd0;
        end else if (fire) begin
            count <= count + 32'd1;
            if (!seen) begin
                stamp <= cyc;
                seen  <= 1'b1;
            end
        end
    end

    assign first_cycle = stamp;
    assign first_seen  = seen;
    assign beats       = count;

endmodule
