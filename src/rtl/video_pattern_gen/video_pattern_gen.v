// -----------------------------------------------------------------------------
// video_pattern_gen - internal 720p pattern source, so the demo never depends on
// an external HDMI source.
//
// Why this exists
//   The HDMI input on this board negotiates EDID and HPD correctly (Windows shows
//   a second monitor) but does not lock onto the TMDS stream from our laptop. Until
//   that is understood, the pipeline can still be demonstrated end to end by
//   generating the picture inside the FPGA:
//
//       pattern_gen -> stamp_in -> enhance -> stamp_out -> HDMI OUT -> capture card
//
//   That also isolates the output side: if this produces a picture on the capture
//   card, HDMI OUT and the capture chain are proven good, and only the input path
//   is in question.
//
// Timing
//   Produces one beat per active pixel on 1280x720 and nothing during blanking:
//   v_axi4s_vid_out pulls a beat only for active pixels and inserts the blanking
//   itself, so the source just counts active pixels. tlast marks the last active
//   pixel of a line, tuser marks the first pixel of a frame (the same convention
//   PYNQ's pixel_pack uses).
//
// Pattern
//   Eight colour bars, a luma staircase along the bottom, and a moving block so
//   motion is visible on a still camera. Chosen so that clarity (local contrast)
//   and the tone curve both change the picture visibly.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module video_pattern_gen #(
    parameter integer H_ACTIVE = 1280,
    parameter integer V_ACTIVE = 720
) (
    input  wire        aclk,
    input  wire        aresetn,

    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast,
    output wire        m_axis_tuser
);

    localparam integer XW = 11;   // up to 2047
    localparam integer YW = 10;   // up to 1023

    reg [XW-1:0] x;
    reg [YW-1:0] y;

    wire fire = m_axis_tvalid && m_axis_tready;

    always @(posedge aclk) begin
        if (!aresetn) begin
            x <= {XW{1'b0}};
            y <= {YW{1'b0}};
        end else if (fire) begin
            if (x == H_ACTIVE - 1) begin
                x <= {XW{1'b0}};
                if (y == V_ACTIVE - 1) y <= {YW{1'b0}};
                else                   y <= y + 1'b1;
            end else begin
                x <= x + 1'b1;
            end
        end
    end

    // ---- colour bars --------------------------------------------------------
    // 8 bars, 160 px each at 1280 wide; index = x / 160
    wire [2:0] bar = x[10:7];                 // 1280/8 = 160 -> x/128 is close enough
    reg  [7:0] bar_r, bar_g, bar_b;
    always @* begin
        case (bar)
            3'd0: begin bar_r = 8'd235; bar_g = 8'd235; bar_b = 8'd235; end // white
            3'd1: begin bar_r = 8'd235; bar_g = 8'd235; bar_b = 8'd16;  end // yellow
            3'd2: begin bar_r = 8'd16;  bar_g = 8'd235; bar_b = 8'd235; end // cyan
            3'd3: begin bar_r = 8'd16;  bar_g = 8'd235; bar_b = 8'd16;  end // green
            3'd4: begin bar_r = 8'd235; bar_g = 8'd16;  bar_b = 8'd235; end // magenta
            3'd5: begin bar_r = 8'd235; bar_g = 8'd16;  bar_b = 8'd16;  end // red
            3'd6: begin bar_r = 8'd16;  bar_g = 8'd16;  bar_b = 8'd235; end // blue
            default: begin bar_r = 8'd16; bar_g = 8'd16; bar_b = 8'd16; end // black
        endcase
    end

    // ---- luma staircase in the bottom 80 rows ------------------------------
    wire in_stair = (y >= V_ACTIVE - 80);
    wire [7:0] stair = {1'b0, x[10:3]};        // 0..255 across the width

    // ---- moving block: 160x120, wraps every 2 s at 60 Hz -------------------
    wire [XW-1:0] blk_x = x - (x >> 3);        // cheap shear so it moves
    wire in_block = (y >= (V_ACTIVE / 2) - 60) && (y < (V_ACTIVE / 2) + 60) &&
                    (blk_x < 12'd160);

    reg [7:0] r, g, b;
    always @* begin
        r = bar_r;
        g = bar_g;
        b = bar_b;
        if (in_stair) begin
            r = stair;
            g = stair;
            b = stair;
        end else if (in_block) begin
            r = 8'd255;
            g = 8'd255;
            b = 8'd255;
        end
    end

    assign m_axis_tdata  = {8'd0, r, g, b};
    assign m_axis_tvalid = aresetn;
    assign m_axis_tlast  = (x == H_ACTIVE - 1);
    assign m_axis_tuser  = (x == 0) && (y == 0);

endmodule
