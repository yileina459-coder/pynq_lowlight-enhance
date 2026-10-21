// -----------------------------------------------------------------------------
// cfg_bram - the two-word configuration memory the kernel reads every pixel.
//
// Why it exists
//   enhance_stream_cfg takes its configuration from a memory port rather than from nine
//   plain input ports. That is what makes a live preset change possible: HLS registers
//   plain inputs in the pipeline prologue, and a free-running kernel runs that prologue
//   once, so the parameters used to freeze at power-up. A memory read cannot be hoisted,
//   so the value stays live.
//
// Why an explicit XPM instead of an inferred array
//   The first version was `(* ram_style = "block" *) reg [63:0] mem [0:1]` with a write port
//   on the 100 MHz PS clock and a read port on the 142.857 MHz pixel clock. With only two
//   entries Vivado inferred *flip-flops*, so the read became a mux of registers and the two
//   clocks made it a synchronous cross-domain path:
//
//       Slack (VIOLATED) -1.393 ns, 59 failing endpoints
//       mem_reg[0][33]/C (clk_fpga_0) -> dout_q_reg[33]/D (clk_fpga_1)
//
//   An explicit xpm_memory_tdpram forces a real block RAM with independent clocks, so the
//   transfer happens inside the primitive (atomic per word) and does not appear as a timed
//   register-to-register path.
//
// Word layout
//   The PS still drives the same axi_gpio pair: channel 1 carries word 0 (clarity / knee /
//   gain_lo / gain_hi) and channel 2 carries word 1 (thresh / binarize / invert / mono /
//   split_x). Those 64 bits are the memory word. It is written only when the value changes,
//   so the BRAM is idle between preset switches.
//
// What the kernel expects (from the generated RTL)
//   cfg_Addr_A is a BYTE address (HLS shifts the word index left by 3), cfg_EN_A is the
//   per-iteration read enable, cfg_Dout_A is the 64-bit data, and cfg_WEN_A is tied to 0
//   because the kernel never writes. Only word 0 is read in practice; word 1 exists so the
//   address cannot be folded away by HLS (see enhance.cpp).
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module cfg_bram (
    // kernel side (ap_clk, 142.857 MHz)
    input  wire        aclk,
    input  wire        en_a,
    input  wire [31:0] addr_a,      // byte address from cfg_Addr_A
    output wire [63:0] dout_a,      // to cfg_Dout_A

    // control side (PS AXI clock, 100 MHz)
    input  wire        pclk,
    input  wire [31:0] cfg_lo,      // gpio_enh_cfg channel 1
    input  wire [31:0] cfg_hi       // gpio_enh_cfg channel 2
);

    wire [63:0] word = {cfg_hi, cfg_lo};

    // Write only when the GPIO value changes, so the memory is idle between switches.
    reg [63:0] word_q;
    initial word_q = 64'd0;
    always @(posedge pclk) begin
        word_q <= word;
    end
    wire we = (word != word_q);

    // Byte address from the kernel: 0 or 8. Two words are decoded.
    wire [1:0] addr_b = addr_a[3:3];

    xpm_memory_tdpram #(
        .ADDR_WIDTH_A        (2),
        .ADDR_WIDTH_B        (2),
        .AUTO_SLEEP_TIME     (0),
        .BYTE_WRITE_WIDTH_A  (64),
        .BYTE_WRITE_WIDTH_B  (64),
        .CASCADE_HEIGHT      (0),
        .CLOCKING_MODE       ("independent_clock"),
        .ECC_MODE            ("no_ecc"),
        .MEMORY_INIT_FILE    ("none"),
        .MEMORY_INIT_PARAM   ("0"),
        .MEMORY_OPTIMIZATION ("true"),
        .MEMORY_PRIMITIVE    ("block"),
        .MEMORY_SIZE         (128),
        .MESSAGE_CONTROL     (0),
        .READ_DATA_WIDTH_A   (64),
        .READ_DATA_WIDTH_B   (64),
        .READ_LATENCY_A      (1),
        .READ_LATENCY_B      (1),
        .READ_RESET_VALUE_A  ("0"),
        .READ_RESET_VALUE_B  ("0"),
        .RST_MODE_A          ("SYNC"),
        .RST_MODE_B          ("SYNC"),
        .SIM_ASSERT_CHK      (0),
        .USE_EMBEDDED_CONSTRAINT (0),
        .USE_MEM_INIT        (0),
        .WAKEUP_TIME         ("disable_sleep"),
        .WRITE_DATA_WIDTH_A  (64),
        .WRITE_DATA_WIDTH_B  (64),
        .WRITE_MODE_A        ("read_first"),
        .WRITE_MODE_B        ("read_first")
    ) cfg_mem (
        .douta      (),
        .doutb      (dout_a),
        .addra      (2'd0),
        .addrb      (addr_b),
        .clka       (pclk),
        .clkb       (aclk),
        .dina       (word),
        .dinb       (64'd0),
        .ena        (we),
        .enb        (en_a),
        .injectsbiterra (1'b0),
        .injectdbiterra (1'b0),
        .regcea     (1'b1),
        .regceb     (1'b1),
        .rsta       (1'b0),
        .rstb       (1'b0),
        .sbiterra   (),
        .dbiterra   (),
        .sleep      (1'b0),
        .wea        (we),
        .web        (1'b0)
    );

endmodule
