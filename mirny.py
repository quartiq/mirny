from migen import *


# increment this if the behavior (LEDs, registers, EEM pins) changes
__proto_rev__ = 0


bus_layout = [
    ("we", 1),
    ("adr", 7),
    ("dat_w", 16),
    ("dat_r", 16),
    ("re", 1),
]

ext_layout = [
    ("cs", 1),
    ("sck", 1),
    ("sdo", 1),
    ("sdi", 1),
]

class CFG(Module):
    def __init__(self, width=None):
        self.bus = Record(bus_layout)
        if width is None:
            width = len(self.bus.dat_w)
        self.cfg = Signal(width)
        self.sync += [
            If(self.bus.we,
                self.cfg.eq(self.bus.dat_w)
            )
        ]
        self.comb += self.bus.dat_r.eq(self.cfg)


class STA(Module):
    def __init__(self, width=None):
        self.bus = Record(bus_layout)
        if width is None:
            width = len(self.bus.dat_w)
        self.sta = Signal(width)
        self.comb += self.bus.dat_r.eq(self.sta)


class REG(Module):
    def __init__(self, width=None):
        self.bus = Record(bus_layout)
        if width is None:
            width = len(self.bus.dat_w)
        self.write = Signal(width)
        self.read = Signal(width)
        self.sync += [
            If(self.bus.we,
                self.write.eq(self.bus.dat_w)
            )
        ]
        self.comb += self.bus.dat_r.eq(self.read)


# R,F edges happen left in each column

# CS   -F__________R
# LI    L
# LO               L
# CLK   _RFRFRFRFRF_
#fMOSI  AABBWW0011
#rSDI    AABBWW0011
#fSTB           11
#fRE      11
#fSDO       0011
#fMISO        0011
#fN     443322110044
#fP     111100000011
# NSRA  0011
# NSRD      001122
#
# default: falling
# MOSI->SDI: rising

# TODO: maybe have combinatorial MISO and a RE-ADR-pipe delay to
# relax timing in the SDI+RE->SDO half cycle path

class SR(Module):
    def __init__(self):
        self.bus = Record(bus_layout)
        self.ext = Record(ext_layout)
        self._slaves = []

        width = len(self.bus.dat_w) + len(self.bus.adr) + 1
        sr_adr = Signal(len(self.bus.adr), reset_less=True)
        sr_dat = Signal(1 + len(self.bus.dat_w), reset_less=True)
        sr_dat_next = Signal(len(sr_dat))
        n = Signal(max=width, reset=width - 1)  # bits to be transferred
        p = Signal(reset=1)  # phase: {1: adr/we, 0: dat}
        re = Signal()
        stb = Signal()
        sdo = Signal(reset_less=True)
        block = Signal(reset_less=True)

        self.comb += [
            sr_dat_next.eq(Cat(self.ext.sdi, sr_dat)),
            stb.eq(n == 0),
            re.eq(n == len(self.bus.dat_w) + 1),

            self.ext.sdo.eq(sdo),
            self.bus.adr[1:].eq(sr_adr[1:]),
            self.bus.adr[0].eq(Mux(p, self.ext.sdi, sr_adr[0])),
            self.bus.dat_w.eq(sr_dat_next),
            self.bus.we.eq(self.ext.cs & stb & sr_dat[-2] & ~block),
            self.bus.re.eq(self.ext.cs & p & re)
        ]
        self.sync += [
            If(self.ext.cs,
                If(~block | ClockSignal("le"),
                    block.eq(0),
                    n.eq(n - 1),
                ),
                If(p,
                    sr_adr[0].eq(self.ext.sdi),
                    If(re,
                        sr_dat[1:].eq(self.bus.dat_r),
                        p.eq(0),
                    ).Else(
                        sr_adr[1:].eq(Cat(self.ext.sdi, sr_adr[1:])),
                    )
                ).Else(
                    sr_dat.eq(sr_dat_next),
                    If(stb,
                        p.eq(p.reset),
                        n.eq(n.reset),
                        block.eq(1),
                    ),
                ),
            ).Else(
                p.eq(p.reset),
                n.eq(n.reset),
            ),
            sdo.eq(sr_dat[-1]),
        ]

    def connect(self, bus, adr, mask):
        adr &= mask
        for _, b_adr, b_mask in self._slaves:
            if intersection((b_adr, b_mask), (adr, mask)):
                raise ValueError("{} intersects {}".format(
                    (adr, mask), (b_adr, b_mask)))
        self._slaves.append((bus, adr, mask))
        stb = Signal()
        self.comb += [
            stb.eq((self.bus.adr & mask) == (adr & mask)),
            bus.adr.eq(self.bus.adr),
            bus.dat_w.eq(self.bus.dat_w),
            bus.we.eq(self.bus.we & stb),
            If(stb,
                self.bus.dat_r.eq(bus.dat_r)
            )
        ]

    def connect_ext(self, ext, adr, mask):
        adr &= mask
        for _, b_adr, b_mask in self._slaves:
            if intersection((b_adr, b_mask), (adr, mask)):
                raise ValueError("{} intersects {}".format(
                    (adr, mask), (b_adr, b_mask)))
        self._slaves.append((ext, adr, mask))
        self.sync += [
            If(self.bus.re,
                ext.cs.eq(self.ext.cs &
                          ((self.bus.adr & mask) == (adr & mask))),
            ),
        ]
        self.comb += [
            ext.sck.eq(self.ext.sck),
            ext.sdi.eq(self.ext.sdi),
            If(ext.cs,
                self.ext.sdo.eq(ext.sdo)
            )
        ]


def intersection(a, b):
    (aa, am), (ba, bm) = a, b
    # TODO
    return False


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

    SPI xfer is ADR(7), WE(1), DAT(REG: 16, ATT: 8, PLL: 32)

    | PREFIX | TARGET |
    |--------+--------|
    | 0 | REG0     |
    | 1 | REG1     |
    | 2 | REG2     |
    | 3 | REG3     |
    | 4 | PLL0     |
    | 5 | PLL1     |
    | 6 | PLL2     |
    | 7 | PLL3     |
    | 8 | ATT0     |
    | 9 | ATT1     |
    | a | ATT2     |
    | b | ATT3     |
    | c | (reserved) all PLL  |
    | d | (reserved) all ATT  |
    | e | (reserved) MEZZ     |
    | f | (reserved) reserved |

    The SPI interface is CPOL=0, CPHA=0, SPI mode 0, 4-wire, full fuplex.

    Configuration register

    The configuration register is updated at last falling SCK edge of the SPI
    transaction. The initial state is 0 (all bits cleared).
    The bits in the configuration register (from LSB to MSB) are:

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | RF_SW     | 4     | Actual RF switch state             |
    | MUXOUT    | 4     | Muxout values                      |
    | IFC_MODE  | 4     | IFC_MODE[0:3]                      |
    | HW_REV    | 2     | HW rev                             |
    | PROTO_REV | 2     | Protocol (see __proto_rev__)       |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | CE        | 4     | Chip enable                        |
    | ATT_RST   | 4     | Attenuator asynchronous reset      |
    | CLK_SEL   | 2     | Selects CLK source: 0 OSC, 1 MMCX, |
    |           |       | 2 reserved, 3 SMA                  |
    | DIV       | 2     | Clock divider configuration:       |
    |           |       | 0: divide-by-one,                  |
    |           |       | 1: reserved,                       |
    |           |       | 2: divider-by-two,                 |
    |           |       | 3: divide-by-four                  |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | RF_SW     | 4     | Activates RF switch                |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | MEZZ_IO   | 8     | Mezzanine IO OI                    |
    | MEZZ_OE   | 8     | Mezzanine IO OE                    |

    Test points
    -----------

    The test points expose miscellaneous signals for debugging and are not part
    of the protocol revision.
    """
    def __init__(self, platform):
        self.comb += platform.request("fsen").eq(1)

        self.eem = eem = []
        for i in range(8):
            tsi = TSTriple()
            eemi = platform.request("eem", i)
            tsi._pin = eemi.io
            self.specials += tsi.get_tristate(eemi.io)
            self.comb += eemi.oe.eq(tsi.oe)
            eem.append(tsi)

        self.clock_domains.cd_sys = ClockDomain("sys", reset_less=True)
        self.clock_domains.cd_sck = ClockDomain("sck", reset_less=True)
        self.clock_domains.cd_le = ClockDomain("le", reset_less=True)

        platform.add_period_constraint(eem[0]._pin, 8.)
        platform.add_period_constraint(eem[3]._pin, 8.)

        self.comb += [
            self.cd_sys.clk.eq(~self.cd_sck.clk),
        ]

        self.specials += [
            Instance("BUFG", i_I=eem[0].i, o_O=self.cd_sck.clk),
            Instance("FDPE", p_INIT=1, i_D=0,
                     i_C=self.cd_sys.clk,
                     i_CE=~eem[3].i,
                     i_PRE=eem[3].i,
                     o_Q=self.cd_le.clk),
        ]

        self.comb += [
            [eem[i].oe.eq(0) for i in range(8) if i not in (2,)],
            eem[2].oe.eq(1),
        ]

        self.submodules.sr = SR()
        self.sync.sck += self.sr.ext.sdi.eq(eem[1].i)
        self.sync.sys += eem[2].o.eq(self.sr.ext.sdo)
        self.comb += [
            self.sr.ext.sck.eq(self.cd_sck.clk),
            self.sr.ext.cs.eq(~eem[3].i),
        ]
        mask = 0b0001111

        regs = [STA(), CFG(), CFG(width=4), REG()]
        self.submodules += regs
        for i, reg in enumerate(regs):
            self.sr.connect(reg.bus, adr=i, mask=mask)

        clk = platform.request("clk")
        clk_div = TSTriple()
        self.specials += clk_div.get_tristate(clk.div)
        # in_sel: 00: XO, 01: MMCX, 10: n/a (SMA+XO), 11: SMA
        # dividers: 00(z): 1, 01(z): 1, 10(low): 2, 11(high) 4
        self.comb += Cat(clk.in_sel, clk_div.o, clk_div.oe).eq(
            regs[1].cfg[8:])

        for i, m in enumerate(platform.request("mezz_io")):
            tsi = TSTriple()
            self.specials += tsi.get_tristate(m)
            self.comb += [
                tsi.o.eq(regs[3].write[i]),
                tsi.oe.eq(regs[3].write[i + 8]),
                regs[3].read[i].eq(tsi.i),
                regs[3].read[i + 8].eq(tsi.oe),
            ]

        ifc_mode = platform.request("ifc_mode")
        hw_rev = platform.request("hw_rev")
        proto_rev = Signal(2, reset=__proto_rev__)
        self.comb += regs[0].sta[8:].eq(Cat(ifc_mode, hw_rev, proto_rev))

        for i in range(4):
            pll = platform.request("pll", i)
            rf_sw = platform.request("rf_sw", i)
            self.comb += [
                rf_sw.eq(regs[2].cfg[i] | eem[4 + i].i),
                regs[0].sta[i].eq(rf_sw),
                regs[0].sta[i + 4].eq(pll.muxout),
            ]

            led = platform.request("led", i)
            self.comb += led.eq(Cat(rf_sw, ~pll.muxout))
            att = platform.request("att", i)
            ext = Record(ext_layout)
            self.comb += [
                pll.ce.eq(regs[1].cfg[i]),
                pll.scki.eq(ext.sck),
                pll.sdi.eq(ext.sdi),
                ext.sdo.eq(pll.muxout),
                pll.le.eq(ext.cs),
            ]
            self.sr.connect_ext(ext, adr=i + 4, mask=mask)
            ext = Record(ext_layout)
            self.comb += [
                att.rstn.eq(regs[1].cfg[i + 4]),
                att.clk.eq(ext.sck),
                att.s_in.eq(ext.sdi),
                ext.sdo.eq(att.s_out),
                att.le.eq(ext.cs),
            ]
            self.sr.connect_ext(ext, adr=i + 8, mask=mask)

        tp = [platform.request("tp", i) for i in range(5)]
        self.comb += [
            tp[0].eq(self.sr._slaves[-1][0].cs),
            tp[1].eq(self.sr._slaves[-1][0].sck),
            tp[2].eq(self.sr._slaves[-1][0].sdi),
            tp[3].eq(self.sr._slaves[-1][0].sdo),
            tp[4].eq(self.sr.bus.we),
        ]
