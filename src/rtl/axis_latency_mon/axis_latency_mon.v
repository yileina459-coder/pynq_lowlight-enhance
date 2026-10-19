// -----------------------------------------------------------------------------
// axis_latency_mon - measures the pipeline fill latency, in pixel clocks.
//
// Why this exists
//   "Latency is about one line, not one frame" is the central claim of this
//   project and until now it was only an architectural argument. This cell turns
//   it into a measured number.
//
// Why it measures a cycle difference and not an in-flight count
//   The first version counted beats that went in but had not come out yet. That
//   is always zero for a pass-through cell: in and out fire in the same cycle, and
//   the pipeline occupancy lives *inside* the kernel where no external counter can
//   see it. Measured on the board it read 0, which is a correct reading of a
//   useless quantity.
//
//   What is observable from the outside is when the first beat goes in and when
//   the matching first beat comes out. Latching the cycle counter at those two
//   events gives the fill latency directly:
//
//       latency_cycles = end_cycle - start_cycle
//       latency_us     = latency_cycles / clock_hz * 1e6
//
//   Both events happen once per PL configuration, so re-loading the overlay
//   re-arms the measurement. The latches are sticky, which is what makes them
//   readable from a slow PS over AXI-Lite without a fast polling loop.
//
// Cost: one 32-bit cycle counter and two 32-bit latches. The stream path is
// combinational, so the monitor adds no latency of its own.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module axis_latency_mon #(
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

    output wire [31:0]         start_cycle,
    output wire [31:0]         end_cycle,
    output wire [31:0]         beats_in,
    output wire [31:0]         beats_out
);

    // Straight through: no register stage, so the monitor cannot change timing
    // behaviour or add latency of its own.
    assign m_axis_tdata   = s_axis_tdata;
    assign m_axis_tkeep   = s_axis_tkeep;
    assign m_axis_tstrb   = s_axis_tstrb;
    assign m_axis_tuser   = s_axis_tuser;
    assign m_axis_tid     = s_axis_tid;
    assign m_axis_tdest   = s_axis_tdest;
    assign m_axis_tlast   = s_axis_tlast;
    assign m_axis_tvalid  = s_axis_tvalid;
    assign s_axis_tready  = m_axis_tready;

    wire in_fire  = s_axis_tvalid && s_axis_tready;
    wire out_fire = m_axis_tvalid && m_axis_tready;

    reg [31:0] cyc;
    always @(posedge aclk) begin
        if (!aresetn) cyc <= 32'd0;
        else          cyc <= cyc + 32'd1;
    end

    reg [31:0] t_start;
    reg [31:0] t_end;
    reg        seen_in;
    reg        seen_out;
    reg [31:0] n_in;
    reg [31:0] n_out;

    always @(posedge aclk) begin
        if (!aresetn) begin
            t_start  <= 32'd0;
            t_end    <= 32'd0;
            seen_in  <= 1'b0;
            seen_out <= 1'b0;
            n_in     <= 32'd0;
            n_out    <= 32'd0;
        end else begin
            if (in_fire) begin
                n_in <= n_in + 32'd1;
                if (!seen_in) begin
                    t_start <= cyc;
                    seen_in <= 1'b1;
                end
            end
            if (out_fire) begin
                n_out <= n_out + 32'd1;
                if (!seen_out) begin
                    t_end    <= cyc;
                    seen_out <= 1'b1;
                end
            end
        end
    end

    assign start_cycle = t_start;
    assign end_cycle   = t_end;
    assign beats_in    = n_in;
    assign beats_out   = n_out;

endmodule
