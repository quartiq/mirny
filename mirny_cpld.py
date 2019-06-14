from migen.build.generic_platform import *
from migen.build.xilinx import XilinxPlatform
from migen.build.xilinx.ise import XilinxISEToolchain

_io = [
        ("tp", 0, Pins("P128")),
        ("tp", 1, Pins("P126")),
        ("tp", 2, Pins("P125")),
        ("tp", 4, Pins("P124")),
        ("tp", 5, Pins("P121")),

        ("ifc_mode", 0, Pins("P102 P103 P104 P105")),

        ("hw_rev", 0, Pins("P119 P120")),

        # fail save LVDS enable, LVDS mode selection
        # high: type 2 receiver, failsafe low
        ("fsen", 0, Pins("P80")),

        ("mezz_io", 0, Pins("P57 P58 P59 P60 P61 P64 P68 P69")),

        ("clk", 0,
            Subsignal("div", Pins("P53")),
            Subsignal("in_sel", Pins("P54 P56")),
        ),

        ("att", 0,
            Subsignal("clk", Pins("P131")),
            Subsignal("le", Pins("P132")),
            Subsignal("rstn", Pins("P130")),
            Subsignal("s_in", Pins("P133")),
            Subsignal("s_out", Pins("P129")),
        ),
        ("pll", 0,
            Subsignal("scki", Pins("P23")),
            Subsignal("sdi", Pins("P22")),
            Subsignal("ce", Pins("P19")),
            Subsignal("le", Pins("P21")),
            Subsignal("muxout", Pins("P24")),
        ),
        ("rf_sw", 0, Pins("P136")),
        ("led", 0, Pins("P110 P111")),

        ("att", 1,
            Subsignal("clk", Pins("P3")),
            Subsignal("le", Pins("P4")),
            Subsignal("rstn", Pins("P2")),
            Subsignal("s_in", Pins("P5")),
            Subsignal("s_out", Pins("P134")),
        ),
        ("pll", 1,
            Subsignal("scki", Pins("P26")),
            Subsignal("sdi", Pins("P32")),
            Subsignal("ce", Pins("P28")),
            Subsignal("le", Pins("P30")),
            Subsignal("muxout", Pins("P25")),
        ),
        ("rf_sw", 1, Pins("P138")),
        ("led", 1, Pins("P112 P113")),

        ("att", 2,
            Subsignal("clk", Pins("P9")),
            Subsignal("le", Pins("P10")),
            Subsignal("rstn", Pins("P7")),
            Subsignal("s_in", Pins("P11")),
            Subsignal("s_out", Pins("P6")),
        ),
        ("pll", 2,
            Subsignal("scki", Pins("P39")),
            Subsignal("sdi", Pins("P43")),
            Subsignal("ce", Pins("P40")),
            Subsignal("le", Pins("P41")),
            Subsignal("muxout", Pins("P35")),
        ),
        ("rf_sw", 2, Pins("P140")),
        ("led", 2, Pins("P115 P116")),

        ("att", 3,
            Subsignal("clk", Pins("P14")),
            Subsignal("le", Pins("P15")),
            Subsignal("rstn", Pins("P13")),
            Subsignal("s_in", Pins("P16")),
            Subsignal("s_out", Pins("P12")),
        ),
        ("pll", 3,
            Subsignal("scki", Pins("P49")),
            Subsignal("sdi", Pins("P52")),
            Subsignal("ce", Pins("P50")),
            Subsignal("le", Pins("P51")),
            Subsignal("muxout", Pins("P45")),
        ),
        ("rf_sw", 3, Pins("P143")),
        ("led", 3, Pins("P117 P118")),

        ("eem", 0,
            Subsignal("io", Pins("P38")),
            Subsignal("oe", Pins("P81"))),
        ("eem", 1,
            Subsignal("io", Pins("P70")),
            Subsignal("oe", Pins("P82"))),
        ("eem", 2,
            Subsignal("io", Pins("P71")),
            Subsignal("oe", Pins("P83"))),
        ("eem", 3,
            Subsignal("io", Pins("P74")),
            Subsignal("oe", Pins("P85"))),
        ("eem", 4,
            Subsignal("io", Pins("P76")),
            Subsignal("oe", Pins("P86"))),
        ("eem", 5,
            Subsignal("io", Pins("P77")),
            Subsignal("oe", Pins("P87"))),
        ("eem", 6,
            Subsignal("io", Pins("P78")),
            Subsignal("oe", Pins("P88"))),
        ("eem", 7,
            Subsignal("io", Pins("P79")),
            Subsignal("oe", Pins("P91"))),
]


class Platform(XilinxPlatform):
    def __init__(self):
        XilinxPlatform.__init__(self, "xc2c128-6-tq144", _io)
        self.toolchain.xst_opt = "-ifmt MIXED"
        self.toolchain.par_opt = ("-optimize speed -unused pullup "
                "-iostd LVCMOS33")
