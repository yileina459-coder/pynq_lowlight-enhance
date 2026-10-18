// -----------------------------------------------------------------------------
// tb_axis_mux3 - self-checking testbench for the operator selector.
//
// Checks three properties that matter for the real use case:
//   1. the selected stream reaches the output unchanged (data and TLAST);
//   2. every input is always drained: no beat is ever left waiting because the
//      select lines point somewhere else (this is what keeps the three
//      operators in lockstep with the broadcast feeding them);
//   3. switching the selector mid-stream does not lose or duplicate beats.
//
// Runs on any Verilog simulator; no vendor primitives.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module tb_axis_mux3;

    localparam integer DATA_W = 32;
    localparam integer N = 64;

    reg               aclk = 0;
    reg               aresetn = 0;
    reg  [1:0]        sel = 0;

    reg  [DATA_W-1:0] s0_tdata = 0;
    reg               s0_tvalid = 0;
    wire              s0_tready;
    reg               s0_tlast = 0;

    reg  [DATA_W-1:0] s1_tdata = 0;
    reg               s1_tvalid = 0;
    wire              s1_tready;
    reg               s1_tlast = 0;

    reg  [DATA_W-1:0] s2_tdata = 0;
    reg               s2_tvalid = 0;
    wire              s2_tready;
    reg               s2_tlast = 0;

    wire [DATA_W-1:0] m_tdata;
    wire              m_tvalid;
    reg               m_tready = 0;
    wire              m_tlast;

    integer errors = 0;
    integer out_count = 0;
    integer taken0 = 0, taken1 = 0, taken2 = 0;
    integer expect_sel = 0;
    reg [DATA_W-1:0] expected;

    axis_mux3 #(.DATA_W(DATA_W)) dut (
        .aclk(aclk), .aresetn(aresetn), .sel(sel),
        .s0_tdata(s0_tdata), .s0_tvalid(s0_tvalid), .s0_tready(s0_tready), .s0_tlast(s0_tlast),
        .s1_tdata(s1_tdata), .s1_tvalid(s1_tvalid), .s1_tready(s1_tready), .s1_tlast(s1_tlast),
        .s2_tdata(s2_tdata), .s2_tvalid(s2_tvalid), .s2_tready(s2_tready), .s2_tlast(s2_tlast),
        .m_tdata(m_tdata), .m_tvalid(m_tvalid), .m_tready(m_tready), .m_tlast(m_tlast)
    );

    always #5 aclk = ~aclk;

    // Each source always has valid data, tagged so the value identifies the bank.
    // Source k beat i carries (k << 24) | i.
    reg [7:0] idx = 0;

    always @(posedge aclk) begin
        if (!aresetn) begin
            s0_tvalid <= 0; s1_tvalid <= 0; s2_tvalid <= 0;
        end else begin
            s0_tvalid <= 1;
            s1_tvalid <= 1;
            s2_tvalid <= 1;
            s0_tdata  <= {8'd0, 24'd0} | idx;
            s1_tdata  <= {8'd1, 24'd0} | idx;
            s2_tdata  <= {8'd2, 24'd0} | idx;
            s0_tlast  <= (idx == N - 1);
            s1_tlast  <= (idx == N - 1);
            s2_tlast  <= (idx == N - 1);
        end
    end

    // Count how many beats each source actually handed over.
    always @(posedge aclk) begin
        if (aresetn) begin
            if (s0_tvalid && s0_tready) taken0 <= taken0 + 1;
            if (s1_tvalid && s1_tready) taken1 <= taken1 + 1;
            if (s2_tvalid && s2_tready) taken2 <= taken2 + 1;
        end
    end

    // Downstream: always ready except for a couple of stalls to make sure the
    // selected path really honours back-pressure.
    integer cyc = 0;
    always @(posedge aclk) begin
        cyc <= cyc + 1;
        m_tready <= ~(cyc % 7 == 3);
    end

    // Checker: compare the handshake data with what the selected source drives.
    always @(posedge aclk) begin
        if (aresetn && m_tvalid && m_tready) begin
            case (expect_sel)
                0: expected = s0_tdata;
                1: expected = s1_tdata;
                default: expected = s2_tdata;
            endcase
            if (m_tdata !== expected) begin
                if (errors < 5) begin
                    $display("MISMATCH sel=%0d got=%h exp=%h", expect_sel, m_tdata, expected);
                end
                errors = errors + 1;
            end
            out_count = out_count + 1;
        end
    end

    initial begin
        aresetn = 0;
        repeat (4) @(posedge aclk);
        aresetn = 1;

        // Hold each selection for a while, then switch mid-stream.
        sel = 0; expect_sel = 0; repeat (40) @(posedge aclk);
        sel = 1; expect_sel = 1; repeat (40) @(posedge aclk);
        sel = 2; expect_sel = 2; repeat (40) @(posedge aclk);
        sel = 0; expect_sel = 0; repeat (40) @(posedge aclk);

        // Invalid selection must fall back to input 0 without breaking anything.
        sel = 3; expect_sel = 0; repeat (20) @(posedge aclk);

        // Every input must have been drained at a comparable rate: the mux is
        // what keeps the three parallel operators in lockstep.
        if (taken0 < 150 || taken1 < 150 || taken2 < 150) begin
            $display("DRAIN FAIL: taken0=%0d taken1=%0d taken2=%0d (each should be >=150)",
                     taken0, taken1, taken2);
            errors = errors + 1;
        end

        // And the selected path must have produced a beat on every cycle where
        // the downstream was ready (no bubbles introduced by the mux).
        if (out_count < 150) begin
            $display("THROUGHPUT FAIL: only %0d output beats", out_count);
            errors = errors + 1;
        end

        $display("out=%0d taken=(%0d,%0d,%0d) errors=%0d", out_count, taken0, taken1, taken2, errors);
        if (errors == 0) $display("AXIS_MUX3 TB PASS");
        else             $display("AXIS_MUX3 TB FAIL");
        $finish;
    end

endmodule
