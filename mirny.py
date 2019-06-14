from migen import *


# increment this if the behavior (LEDs, registers, EEM pins) changes
__proto_rev__ = 8


class SR(Module):
    """
    Shift register, SPI slave

    * CPOL = 0 (clock idle low during ~SEL)
    * CPHA = 0 (sample on first edge, shift on second)
    * SPI mode 0
    * samples SDI on rising clock edges (SCK1 domain)
    * shifts out SDO on falling clock edges (SCK0 domain)
    * MSB first
    * the first output bit (MSB) is undefined
    * the first output bit is available from the start of the SEL cycle until
      the first falling edge
    * the first input bit is sampled on the first rising edge
    * on the first rising edge with SEL assered, the parallel data DO
      is loaded into the shift register
    * following at least one rising clock edge, on the deassertion of SEL,
      the shift register is loaded into the parallel data register DI
    """
    def __init__(self, adr_width=8, width=32):
        self.sdi = Signal()
        self.sdo = Signal()
        self.sel = Signal()

        self.adr = Signal(adr_width)
        self.di = Signal(width)
        self.do = Signal(width)

        # # #

        sr = Signal(width)

        self.clock_domains.cd_le = ClockDomain("le", reset_less=True)
        # clock the latch domain from selection deassertion but only after
        # there was a serial clock edge with asserted select (i.e. ignore
        # glitches).
        self.specials += Instance("FDPE", p_INIT=1,
                i_D=0, i_C=ClockSignal("sck1"), i_CE=self.sel, i_PRE=~self.sel,
                o_Q=self.cd_le.clk)

        self.sync.sck0 += [
                If(self.sel,
                    self.sdo.eq(sr[-1]),

                )
        ]
        self.sync.sck1 += [
                If(self.sel,
                    sr[0].eq(self.sdi),
                    If(self.cd_le.clk,
                        sr[1:].eq(self.do[:-1])
                    ).Else(
                        sr[1:].eq(sr[:-1])
                    )
                )
        ]
        self.sync.le += [
                self.di.eq(sr)
        ]


class CFG(Module):
    """Configuration register

    The configuration register is updated at last falling SCK edge of the SPI
    transaction. The initial state is 0 (all bits cleared).
    The bits in the configuration register (from LSB to MSB) are:

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | RF_SW     | 4     | Activates RF switch                |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | CE        | 4     | Chip enable                        |
    | MASK_RLED | 4     | Mask VCO ~MUXOUT to RLED           |
    | MASK_LE   | 4     | Mask VCO latch enable              |
    | CLK_SEL   | 2     | Selects CLK source: 0 OSC, 1 MMCX, |
    |           |       | 2 reserved, 3 SMA                  |
    | DIV       | 2     | Clock divider configuration:       |
    |           |       | 0: divide-by-one,                  |
    |           |       | 1: reserved,                       |
    |           |       | 2: divider-by-two,                 |
    |           |       | 3: divide-by-four                  |
    | ATT_RST   | 1     | Attenuator asynchronous reset      |
    |           | 1     | reserved                           |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | RLED      | 4     | Activates the red LED              |
    | GLED      | 4     | Activates the green LED            |

    | Name      | Width | Function                                  |
    |-----------+-------+-------------------------------------------|
    | RF_SW     | 4     | Actual RF switch and green LED activation |
    |           |       | (including that by EEM0.SW[4:8])          |
    | MUXOUT    | 4     | Muxout values                             |
    | IFC_MODE  | 4     | IFC_MODE[0:3]                             |
    | PROTO_REV | 4     | Protocol revision (see __proto_rev__)     |
    | HW_REV    | 2     | HW rev
    """
    def __init__(self, platform, n=4):
        self.data = Record([
            ("rf_sw", n),
            ("led", n),

            ("profile", 3),

            ("dummy", 1),
            ("io_update", 1),

            ("mask_nu", 4),

            ("clk_sel0", 1),
            ("sync_sel", 1),

            ("rst", 1),
            ("io_rst", 1),
            ("clk_sel1", 1),
            ("div", 2),
        ])


class Mirny(Module):
    """
    Mirny IO router and configuration/status
    =========================================

    Pin Out
    -------

    | EEM LVDS pair | Function     |
    |---------------+--------------|
    | EEM 0         | SCLK         |
    | EEM 1         | MOSI         |
    | EEM 2         | MISO, MUXOUT |
    | EEM 3         | CS           |
    | EEM 4         | SW0          |
    | EEM 5         | SW1          |
    | EEM 6         | SW3          |
    | EEM 7         | SW4          |

    IFC_MODE
    --------

    all reserved

    SPI
    ---

    | PREFIX | TARGET |
    |--------+--------|
    | 0 | PLL0     |
    | 1 | PLL1     |
    | 2 | PLL2     |
    | 3 | PLL3     |
    | 4 | ATT0     |
    | 5 | ATT0     |
    | 6 | ATT0     |
    | 7 | ATT0     |
    | 8 | CFG0     |
    | 9 | CFG0     |
    | a | CFG0     |
    | b | CFG0     |
    | c | all PLL  |
    | d | all ATT  |
    | e | reserved |
    | f | reserved |

    The SPI interface is CPOL=0, CPHA=0, SPI mode 0, 4-wire, full fuplex.

    Test points
    -----------

    The test points expose miscellaneous signals for debugging and are not part
    of the protocol revision.
    """
    def __init__(self, platform):
        clk = platform.request("clk")
 
        ts_clk_div = TSTriple()
        self.specials += [
                ts_clk_div.get_tristate(clk.div)
        ]
        # TODO
        self.comb += [
            clk.in_sel.eq(0b00),  # VCO
            # dividers: z: 1, 0: 2, 1: 4
            ts_clk_div.oe.eq(0),  # div-1
            ts_clk_div.o.eq(0),  # div-1
        ]
       
        # TODO
        # mezz_io = platform.request("mezz_io")
        # ifc_mode = platform.request("ifc_mode")
        # hw_rev = platform.request("hw_rev")

        att = [platform.request("att", i) for i in range(4)]
        pll = [platform.request("pll", i) for i in range(4)]
        rf_sw = [platform.request("rf_sw", i) for i in range(4)]
        led = [platform.request("led", i) for i in range(4)]

        # TODO
        for rf_sw_i, ledi, plli in zip(rf_sw, led, pll):
            self.comb += [
                ledi[1].eq(~plli.muxout),
                ledi[0].eq(rf_sw_i),
                rf_sw_i.eq(1),
            ]

        self.comb += platform.request("fsen").eq(1)

        self.eem = eem = []
        for i in range(8):
            tsi = TSTriple()
            eemi = platform.request("eem", i)
            tsi._pin = eemi.io
            self.specials += tsi.get_tristate(eemi.io)
            self.comb += eemi.oe.eq(tsi.oe)
            eem.append(tsi)

        # AD9910 only
        self.clock_domains.cd_sys = ClockDomain("sys", reset_less=True)
        self.clock_domains.cd_sck0 = ClockDomain("sck0", reset_less=True)
        self.clock_domains.cd_sck1 = ClockDomain("sck1", reset_less=True)
        self.clock_domains.cd_sel0 = ClockDomain("sel0", reset_less=True)
        self.clock_domains.cd_sel1 = ClockDomain("sel1", reset_less=True)

        platform.add_period_constraint(eem[0]._pin, 8.)
        platform.add_period_constraint(eem[3]._pin, 8.)

        self.specials += [
            Instance("BUFG", i_I=eem[0].i, o_O=self.cd_sck1.clk),
            Instance("FDPE", p_INIT=1,
                i_D=0,
                i_C=self.cd_sck1.clk,
                i_CE=self.cd_sel1.clk,
                i_PRE=~self.cd_sel1.clk,
                o_Q=self.cd_sel0.clk),
        ]
        self.comb += [
            self.cd_sck0.clk.eq(~self.cd_sck1.clk),
            self.cd_sys.clk.eq(self.cd_sck1.clk),
            self.cd_sel1.clk.eq(~eem[3].i),
        ]

        self.comb += [
            [eem[i].oe.eq(0) for i in range(8) if i not in (2,)],
            eem[2].oe.eq(1),
        ]
        return

        cfg = CFG(platform)
        stat = Status(platform)
        sr = SR(24)
        assert len(cfg.data) <= len(sr.di)
        assert len(stat.data) <= len(sr.do)
        self.submodules += cfg, stat, sr

        sel = Signal(8)
        cs = Signal(3)
        miso = Signal(8)
        mosi = eem[1].i


        self.comb += [
                cfg.en_9910.eq(en_9910),
                cs.eq(Cat(eem[3].i, eem[4].i, ~en_nu & eem[5].i)),
                Array(sel)[cs].eq(1),  # one-hot
                eem[2].o.eq(Array(miso)[cs]),
                miso[3].eq(miso[4]),  # for all-DDS take DDS0:MISO

                att.clk.eq(sel[2] & self.cd_sck1.clk),
                att.s_in.eq(mosi),
                miso[2].eq(att.s_out),

                sr.sel.eq(sel[1]),
                sr.sdi.eq(mosi),
                miso[1].eq(sr.sdo),

                cfg.data.raw_bits().eq(sr.di),
                sr.do.eq(stat.data.raw_bits()),
        ]
        for i, ddsi in enumerate(dds):
            sel_spi = Signal()
            sel_nu = Signal()
            self.comb += [
                    sel_spi.eq(sel[i + 4] | (sel[3] & cfg.data.mask_nu[i])),
                    sel_nu.eq(en_nu & ~cfg.data.mask_nu[i]),
                    ddsi.cs_n.eq(~Mux(sel_nu, eem[5].i, sel_spi)),
                    ddsi.sck.eq(Mux(sel_nu, eem[2].i, self.cd_sck1.clk)),
                    ddsi.sdi.eq(Mux(sel_nu, eem[i + 8].i, mosi)),
                    miso[i + 4].eq(ddsi.sdo),
                    ddsi.io_update.eq(Mux(cfg.data.mask_nu[i],
                        cfg.data.io_update, eem[6].i)),
            ]

        tp = [platform.request("tp", i) for i in range(5)]
        self.comb += [
        ]
