module smoke_top (
    input  wire clk,
    input  wire rst,
    input  wire a,
    input  wire b,
    output reg  y
);
    reg [7:0] cnt;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 8'd0;
            y   <= 1'b0;
        end else begin
            cnt <= cnt + 8'd1;
            y   <= a ^ b ^ cnt[0];
        end
    end
endmodule
