from migen import *


# increment this if the behavior (LEDs, registers, EEM pins) changes
__proto_rev__ = 0


class AsyncRst(Module):
    def __init__(self, width=None, cd="sys", reset=0, **kwargs):
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


class REG(Module):
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


# R,F edges happen left in each column

# CSN  -F__________R
# LI    L
# LO               L
# CLK   _RFRFRFRFRF_
#fMOSI  AABBWW0011
#rSDI    AABBWW0011
#fWE            WW
#fRE        11
#fSDO         0011
#fMISO        0011
#fN     443322110004
#fN A   332211000003
#fN D   222222221102
#
# default: falling
# MOSI->SDI: rising

class SR(Module):
    def __init__(self):
        self.bus = Record(bus_layout)
        self.ext = Record(ext_layout)

        self._slaves = []

        sdi = Signal(reset_less=True)
        sr_adr = Signal(len(self.bus.adr), reset_less=True)
        sr_dat = Signal(len(self.bus.dat_w), reset_less=True)
        we = Signal(reset_less=True)

        width = len(sr_adr) + 1 + len(sr_dat)
        # bits to be transferred - 1
        n = AsyncRst(max=width, reset=width - 1)
        p = AsyncRst()
        self.submodules += n, p

        self.comb += [
            n.i.eq(n.o - 1),
            n.ce.eq(n.o != 0),
            p.i.eq(1),
            p.ce.eq(n.o == len(sr_dat)),

            self.ext.sdo.eq(sr_dat[-1]),

            self.bus.adr.eq(sr_adr),
            self.bus.dat_w.eq(Cat(sdi, sr_dat)),
            self.bus.re.eq(p.ce),
            self.bus.we.eq(~n.ce & we),
        ]
        self.sync.sck += sdi.eq(self.ext.sdi)
        self.sync += [
            sr_dat.eq(self.bus.dat_w),
            If(p.ce,
                we.eq(sdi),
                sr_dat.eq(self.bus.dat_r),
            ).Elif(~p.o,
                sr_adr.eq(Cat(sdi, sr_adr)),
            )
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
        stb = AsyncRst()
        self.submodules += stb
        self.comb += [
            stb.i.eq(self.bus.adr & mask == adr),
            stb.ce.eq(self.bus.re),
            # don't glitch with &stb.o
            ext.sck.eq(self.ext.sck),
            ext.sdi.eq(self.ext.sdi & stb.o),
            ext.cs.eq(stb.o),
            If(stb.o,
                self.ext.sdo.eq(ext.sdo),
            ),
        ]

    def connect_almazny_passthrough(self, pt, adr, mask):
        # for use w/ almazny
        self._check_intersection(adr, mask)
        self._slaves.append((pt, adr, mask))
        stb = AsyncRst()
        self.submodules += stb

        saved_adr = Signal(2)
        latch_signal = Signal()

        self.comb += [
            stb.i.eq(((self.bus.adr & adr) == adr) & (self.ext.cs)),
            stb.ce.eq(self.bus.re),
            pt.mosi.eq(self.ext.sdi & stb.o),
            pt.clk.eq(self.ext.sck & stb.o),
            # simple solution - latch after writing is done
            latch_signal.eq(~stb.o),
        ]

        # update saved address when we write to almazny
        self.sync += [
            If(stb.o,
                saved_adr.eq(self.bus.adr[:2]),
            )
        ]

        # latch can stay up indefinitely, it's only rising edge that counts
        self.comb += [
            pt.lt1.eq((saved_adr == 0) & latch_signal),
            pt.lt2.eq((saved_adr == 1) & latch_signal),
            pt.lt3.eq((saved_adr == 2) & latch_signal),
            pt.lt4.eq((saved_adr == 3) & latch_signal),
        ]


def intersection(a, b):
    (aa, am), (ba, bm) = a, b
    # TODO
    return False


class Mirny(Module):
    """
    Mirny IO router and configuration/status
    ========================================

    Pin Out
    -------

    | EEM LVDS pair | Function               |
    |---------------+------------------------|
    | EEM 0         | SCLK                   |
    | EEM 1         | MOSI                   |
    | EEM 2         | MISO, MUXOUT           |
    | EEM 3         | CS                     |
    | EEM 4         | SW0, MUXOUT0, MEZZ_IO0 |
    | EEM 5         | SW1, MUXOUT1, MEZZ_IO1 |
    | EEM 6         | SW2, MUXOUT2, MEZZ_IO2 |
    | EEM 7         | SW3, MUXOUT3, MEZZ_IO3 |

    SPI
    ---

    SPI xfer is ADR(7), WE(1), DAT(REG: 16, ATT: 8, PLL: 32, SR: 8)

    | ADR | TARGET        |
    |-----+---------------|
    | 0   | REG0          |
    | 1   | REG1          |
    | 2   | REG2          |
    | 3   | REG3          |
    | 4   | PLL0          |
    | 5   | PLL1          |
    | 6   | PLL2          |
    | 7   | PLL3          |
    | 8   | ATT0          |
    | 9   | ATT1          |
    | a   | ATT2          |
    | b   | ATT3          |
    | c   | (Almazny) SR1 |
    | d   | (Almazny) SR2 |
    | e   | (Almazny) SR3 |
    | f   | (Almazny) SR4 |

    The SPI interface is CPOL=0, CPHA=0, SPI mode 0, 4-wire, full fuplex.

    Configuration register

    The status bits are read on the falling edge of after the WE bit (8th
    falling edge).
    The configuration bits are updated at the last falling SCK edge of the SPI
    transaction (24th falling edge). The initial state is 0 (all bits cleared).
    The bits in the registers (from LSB to MSB) are:

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | HW_REV    | 2     | HW rev                             |
    | PROTO_REV | 2     | Protocol (see __proto_rev__)       |
    | IFC_MODE  | 4     | IFC_MODE[0:4]                      |
    | MUXOUT    | 4     | Muxout values                      |

    | Name      | Width | Function                           |
    |-----------+-------+------------------------------------|
    | CE_N      | 4     | PLL chip enable (bar)              |
    | CLK_SEL   | 2     | Selects CLK source:                |
    |           |       | 0 OSC, 1 reserved, 2 MMCX, 3 SMA   |
    | DIV       | 2     | Clock divider configuration:       |
    |           |       | 0: divide-by-one,                  |
    |           |       | 1: reserved,                       |
    |           |       | 2: divider-by-two,                 |
    |           |       | 3: divide-by-four                  |
    | ATT_RST   | 1     | Attenuator reset                   |
    | FSEN_N    | 1     | LVDS fail safe, Type 2 (bar)       |
    | MUXOUT_EEM| 1     | route MUXOUT to EEM[4:8]           |
    | EEM_MEZZIO| 1     | route EEM[4:8] to MEZZ_IO[0:4]     |
    | ALMAZNY_OE| 1     | Almazny OE in legacy almazny mode  |

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
    def __init__(self, platform, legacy_almazny=False):
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
        mask = 0b0001111

        self.comb += [
            self.sr.ext.sck.eq(self.cd_sck.clk),
            self.sr.ext.sdi.eq(eem[1].i),
            eem[2].o.eq(self.sr.ext.sdo),
            self.sr.ext.cs.eq(eem[3].i),
        ]

        regs = [REG(), REG(width=13), REG(width=4), REG()]
        self.submodules += regs
        for i, reg in enumerate(regs):
            self.sr.connect(reg.bus, adr=i, mask=mask)

        self.comb += [
            regs[0].read[:8].eq(Cat(
                platform.request("hw_rev"),
                Constant(__proto_rev__, 2),
                platform.request("ifc_mode"),
            )),
            regs[1].read.eq(regs[1].write),
            regs[2].read.eq(regs[2].write),
        ]

        clk = platform.request("clk")
        clk_div = TSTriple()
        self.specials += clk_div.get_tristate(clk.div)
        # in_sel: 00: XO, 01: n/a (SMA+XO), 10: MMCX, 11: SMA
        # dividers: 00(z): 1, 01(z): 1, 10(low): 2, 11(high) 4
        self.comb += [
            Cat(clk.in_sel, clk_div.o, clk_div.oe).eq(regs[1].write[4:8]),
            platform.request("fsen").eq(~regs[1].write[9]),
        ]

        if legacy_almazny:
            # 6 signals
            almazny_io = platform.request("legacy_almazny_io")
            almazny_adr = 0b1100  # 1100 - and then 1101, 1110, 1111 for sr 1-4
            almazny_mask = 0b0011
            self.sr.connect_almazny_passthrough(almazny_io, almazny_adr, almazny_mask)

            # 7th, connecting all NOEs
            for i in range(4):
                pin = platform.request("legacy_almazny_noe", i)
                tsi = TSTriple()
                self.specials += tsi.get_tristate(pin)
                self.comb += [ 
                    tsi.o.eq(~regs[1].write[12]),
                    tsi.oe.eq(1)
                ]

            # hardcode SRCLR#
            srclr = platform.request("legacy_almazny_srclr")
            self.comb += srclr.eq(1)
        else:
            for i, m in enumerate(platform.request("mezz_io")):
                tsi = TSTriple()
                self.specials += tsi.get_tristate(m)
                self.comb += [
                    tsi.o.eq(regs[3].write[i] | (0 if i >= 4 else
                        (regs[1].write[11] & eem[i + 4].i))),
                    regs[3].read[i].eq(tsi.i),
                    tsi.oe.eq(regs[3].write[i + 8]),
                    regs[3].read[i + 8].eq(tsi.oe),
                ]

        for i in range(4):
            rf_sw = platform.request("rf_sw", i)
            self.comb += [
                rf_sw.eq(regs[2].write[i] | (
                    ~regs[1].write[11] & ~regs[1].write[10] & eem[4 + i].i)),
                eem[4 + i].oe.eq(regs[1].write[10]),
            ]

            pll = platform.request("pll", i)
            ext = Record(ext_layout)
            self.sr.connect_ext(ext, adr=i + 4, mask=mask)
            self.comb += [
                pll.ce.eq(~regs[1].write[i]),
                pll.scki.eq(ext.sck),
                pll.sdi.eq(ext.sdi),
                ext.sdo.eq(pll.muxout),
                regs[0].read[i + 8].eq(pll.muxout),
                eem[4 + i].o.eq(pll.muxout),
                pll.le.eq(~ext.cs),
            ]

            self.comb += platform.request("led", i).eq(
                Cat(rf_sw, ~pll.muxout & ~regs[1].write[10]))

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
            tp[0].eq(self.sr.ext.sck),
            tp[1].eq(eem[1].i),
            tp[2].eq(eem[2].i),
            tp[3].eq(self.sr.bus.re),
            tp[4].eq(self.sr.bus.we),
        ]
