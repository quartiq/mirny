from migen import *


# increment this if the behavior (LEDs, registers, EEM pins) changes
__proto_rev__ = 0


class AsyncRst(Module):
    def __init__(self, width=1, cd="sys", reset=0, **kwargs):
        self.i = Signal(width, reset=reset, **kwargs)
        self.o = Signal(width, **kwargs)
        self.ce = Signal(reset=1)
        for i in range(len(self.i)):
            ini = (reset >> i) & 1
            self.specials += Instance("FDCPE",
                                      p_INIT=ini,
                                      i_D=self.i[i],
                                      i_C=ClockSignal(cd),
                                      i_CE=self.ce,
                                      i_PRE=ResetSignal(cd) if ini else 0,
                                      i_CLR=ResetSignal(cd) if not ini else 0,
                                      o_Q=self.o[i])


bus_layout = [
    ("adr", 7),
    ("re", 1),
    ("dat_r", 16),
    ("we", 1),
    ("dat_w", 16),
]

ext_layout = [
    ("cs", 1),
    ("sck", 1),
    ("sdo", 1),
    ("sdi", 1),
]


class RW(Module):
    def __init__(self, width=None, read=True, write=True):
        self.bus = Record(bus_layout)
        if width is None:
            width = len(self.bus.dat_w)
        assert width <= len(self.bus.dat_w)
        if write:
            self.write = Signal(width)
            self.sync.reg += If(self.bus.we, self.write.eq(self.bus.dat_w))
        if read:
            self.read = Signal(width)
            self.comb += self.bus.dat_r.eq(self.read)


class REG(RW):
    def __init__(self, width=None):
        super().__init__(width, read=True, write=True)
        self.comb += self.read.eq(self.write)


# R,F edges happen left in each column

# CSN  -F__________R
# LI    L
# LO               L
# CLK   _RFRFRFRFRF_
#fMOSI  AABBWW0011
#rSDI    AABBWW0011
#fSTB           11
#fRE        11
#fSDO         0011
#fMISO        0011
#fN     443322110044
#fP     111100000011
# NSRA  0011
# NSRD      001122
#
# default: falling
# MOSI->SDI: rising

class SR(Module):
    def __init__(self):
        self.bus = Record(bus_layout)
        self.ext = Record(ext_layout)

        self._slaves = []
        width = len(self.bus.dat_w) + len(self.bus.adr) + 1
        sr_adr = Signal(1 + len(self.bus.adr), reset_less=True)
        sr_dat = Signal(len(self.bus.dat_w), reset_less=True)
        sr_dat_next = Signal(len(sr_dat))
        # bits to be transferred - 1
        n_adr = AsyncRst(None, max=len(sr_adr), reset=-1)
        n_dat = AsyncRst(None, max=len(sr_dat), reset=-1)
        self.submodules += n_adr, n_dat
        re = Signal()
        stb = Signal()
        sdi = Signal(reset_less=True)

        self.comb += [
            n_adr.i.eq(n_adr.o - 1),
            n_adr.ce.eq(n_adr.o != 0),
            n_dat.i.eq(n_dat.o - 1),
            n_dat.ce.eq(~n_adr.ce & (n_dat.o != 0)),

            sr_dat_next.eq(Cat(sdi, sr_dat)),
            self.ext.sdo.eq(sr_dat[-1]),

            self.bus.adr.eq(sr_adr[1:]),
            self.bus.dat_w.eq(sr_dat_next),
            self.bus.we.eq(n_dat.ce & sr_adr[0]),
            self.bus.re.eq(n_adr.o == 1)
        ]
        self.sync.sck += sdi.eq(self.ext.sdi)
        self.sync += [
            If(n_adr.ce,
                sr_adr.eq(Cat(sdi, sr_adr)),
            ),
            If(self.bus.re,
                sr_dat.eq(self.bus.dat_r),
            ),
            If(n_dat.ce,
                sr_dat.eq(sr_dat_next),
            ),
        ]

    def _check_intersection(self, adr, mask):
        for _, b_adr, b_mask in self._slaves:
            if intersection((b_adr, b_mask), (adr, mask)):
                raise ValueError("{} intersects {}".format(
                    (adr, mask), (b_adr, b_mask)))

    def connect(self, bus, adr, mask):
        adr &= mask
        self._check_intersection(adr, mask)
        self._slaves.append((bus, adr, mask))
        stb = Signal()
        self.comb += [
            stb.eq(self.bus.adr & mask == adr),
            bus.adr.eq(self.bus.adr),
            bus.dat_w.eq(self.bus.dat_w),
            bus.we.eq(self.bus.we & stb),
            bus.re.eq(self.bus.re & stb),
            If(stb,
                self.bus.dat_r.eq(bus.dat_r)
            )
        ]

    def connect_ext(self, ext, adr, mask):
        adr &= mask
        self._check_intersection(adr, mask)
        self._slaves.append((ext, adr, mask))
        stb = AsyncRst(1)
        self.submodules += stb
        self.comb += [
            stb.i.eq(self.bus.adr & mask == adr),
            stb.ce.eq(self.bus.re),
            ext.sck.eq(self.ext.sck),  # do not glitch with stb.o
            ext.sdi.eq(self.ext.sdi),
            ext.cs.eq(stb.o),
            If(stb.o,
                self.ext.sdo.eq(ext.sdo),
            ),
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

    | ADR | TARGET |
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
    | f | reserved |

    The SPI interface is CPOL=0, CPHA=0, SPI mode 0, 4-wire, full fuplex.

    Configuration register

    The configuration registers is updated at last falling SCK edge of the SPI
    transaction. The initial state is 0 (all bits cleared).
    The bits in the configuration registers (from LSB to MSB) are:

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | MUXOUT    | 4     | Muxout values                      |
    | IFC_MODE  | 4     | IFC_MODE[0:3]                      |
    |           | 2     | reserved                           |
    | HW_REV    | 2     | HW rev                             |
    | PROTO_REV | 4     | Protocol (see __proto_rev__)       |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | CE_N      | 4     | PLL chip enable (bar)              |
    | CLK_SEL   | 2     | Selects CLK source: 0 OSC, 1 MMCX, |
    |           |       | 2 reserved, 3 SMA                  |
    | DIV       | 2     | Clock divider configuration:       |
    |           |       | 0: divide-by-one,                  |
    |           |       | 1: reserved,                       |
    |           |       | 2: divider-by-two,                 |
    |           |       | 3: divide-by-four                  |
    | ATT_RST   | 1     | Attenuator reset                   |
    | FSEN_N    | 1     | LVDS fail safe, Type 2 (bar)       |
    |           | 2     | reserved                           |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | RF_SW     | 4     | RF switch state                    |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | MEZZ_IO   | 8     | Mezzanine IO                       |
    | MEZZ_OE   | 8     | Mezzanine OE                       |

    Test points
    -----------

    The test points expose miscellaneous signals for debugging and are not part
    of the protocol revision.
    """
    def __init__(self, platform):
        self.eem = eem = []
        for i in range(8):
            tsi = TSTriple()
            eemi = platform.request("eem", i)
            tsi._pin = eemi.io
            eem.append(tsi)
            self.specials += tsi.get_tristate(eemi.io)
            self.comb += [
                eemi.oe.eq(tsi.oe),
                tsi.oe.eq(i in (2,)),
            ]

        platform.add_period_constraint(eem[0]._pin, 8.)
        platform.add_period_constraint(eem[3]._pin, 8.)

        self.clock_domains.cd_sys = ClockDomain("sys")
        self.clock_domains.cd_sck = ClockDomain("sck")
        self.clock_domains.cd_reg = ClockDomain("reg", reset_less=True)

        self.specials += [
            Instance("BUFG",
                     i_I=eem[0].i,
                     o_O=self.cd_sck.clk),
        ]
        self.comb += [
            self.cd_sck.rst.eq(~eem[3].i),
            self.cd_sys.clk.eq(~self.cd_sck.clk),
            self.cd_sys.rst.eq(self.cd_sck.rst),
            self.cd_reg.clk.eq(self.cd_sys.clk),
        ]

        self.submodules.sr = SR()
        self.comb += [
            self.sr.ext.sck.eq(self.cd_sck.clk),
            self.sr.ext.sdi.eq(eem[1].i),
            eem[2].o.eq(self.sr.ext.sdo),
            self.sr.ext.cs.eq(eem[3].i),
        ]
        mask = 0b0001111

        regs = [
            RW(width=16),
            REG(width=12),
            RW(width=4),
            RW(width=16)
        ]
        self.submodules += regs
        for i, reg in enumerate(regs):
            self.sr.connect(reg.bus, adr=i, mask=mask)

        clk = platform.request("clk")
        clk_div = TSTriple()
        self.specials += clk_div.get_tristate(clk.div)
        # in_sel: 00: XO, 01: MMCX, 10: n/a (SMA+XO), 11: SMA
        # dividers: 00(z): 1, 01(z): 1, 10(low): 2, 11(high) 4
        self.comb += Cat(clk.in_sel, clk_div.o, clk_div.oe).eq(
            regs[1].write[4:8])

        for i, m in enumerate(platform.request("mezz_io")):
            tsi = TSTriple()
            self.specials += tsi.get_tristate(m)
            self.comb += [
                tsi.o.eq(regs[3].write[i]),
                tsi.oe.eq(regs[3].write[i + 8]),
                regs[3].read[i].eq(tsi.i),
                regs[3].read[i + 8].eq(tsi.oe),
            ]

        self.comb += platform.request("fsen").eq(~regs[1].write[9])

        ifc_mode = platform.request("ifc_mode")
        hw_rev = platform.request("hw_rev")
        self.comb += regs[0].read[4:].eq(
            Cat(ifc_mode, Constant(0, 2), hw_rev, Constant(__proto_rev__, 4)))

        for i in range(4):
            rf_sw = platform.request("rf_sw", i)
            self.comb += [
                rf_sw.eq(regs[2].write[i] | eem[4 + i].i),
                regs[2].read[i].eq(rf_sw),
            ]

            pll = platform.request("pll", i)
            ext = Record(ext_layout)
            self.sr.connect_ext(ext, adr=i + 4, mask=mask)
            self.comb += [
                pll.ce.eq(~regs[1].write[i]),
                pll.scki.eq(ext.sck),
                pll.sdi.eq(ext.sdi),
                ext.sdo.eq(pll.muxout),
                pll.le.eq(~ext.cs),
            ]

            led = platform.request("led", i)
            self.comb += [
                led.eq(Cat(rf_sw, ~pll.muxout)),
                regs[0].read[i].eq(pll.muxout),
            ]

            att = platform.request("att", i)
            ext = Record(ext_layout)
            self.sr.connect_ext(ext, adr=i + 8, mask=mask)
            self.comb += [
                att.rstn.eq(~regs[1].write[8]),
                att.clk.eq(ext.sck),
                att.s_in.eq(ext.sdi),
                ext.sdo.eq(att.s_out),
                att.le.eq(~ext.cs),
            ]

        tp = [platform.request("tp", i) for i in range(5)]
        self.comb += [
            tp[0].eq(self.sr._slaves[4][0].cs),
            tp[1].eq(self.sr._slaves[4][0].sck),
            tp[2].eq(self.sr._slaves[4][0].sdi),
            tp[3].eq(self.sr.bus.re),
            tp[4].eq(self.sr.bus.we),
        ]
