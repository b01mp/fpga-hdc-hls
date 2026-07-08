"""
datatypes.py -- per-datatype op cost (the Novelty 1 tie-in).

The SAME primitive costs different hardware depending on the datatype family:
a binary bind is an XOR (~1 LUT), a fixed/integer bind is a multiply (~1 DSP).
This module turns that into numbers, so the estimator can *quantify* why bipolar
/ fixed cost more than binary -- making the datatype-parametric novelty measurable.

Everything returns a `Resources` bundle (LUT / FF / DSP / BRAM / URAM). The named
constants at the top are the knobs calibrate.py will fit against real csynth data.
"""
from dataclasses import dataclass
import math

FAMILIES = ("binary", "bipolar", "fixed", "integer", "pow2")

# ---- calibratable cost constants (per single-element lane) ------------------
LUT_PER_XOR      = 1      # binary bind: one XOR gate
LUT_PER_SIGN_MUL = 2      # bipolar bind: (+/-1)*(+/-1) is sign logic, not a DSP
LUT_PER_BIT      = 1      # ripple adder / comparator ~ 1 LUT per bit
DSP_PER_MUL      = 1      # fixed/integer multiply up to DSP_MUL_MAXBITS wide
DSP_MUL_MAXBITS  = 18     # one DSP48 handles ~18-bit multiplies


@dataclass
class Resources:
    """A bundle of FPGA resources. Supports + (combine) and .scale(k) (replicate)."""
    lut: float = 0.0
    ff: float = 0.0
    dsp: float = 0.0
    bram36: float = 0.0
    uram: float = 0.0

    def __add__(self, o):
        return Resources(self.lut + o.lut, self.ff + o.ff, self.dsp + o.dsp,
                         self.bram36 + o.bram36, self.uram + o.uram)

    def scale(self, k):
        return Resources(self.lut * k, self.ff * k, self.dsp * k,
                         self.bram36 * k, self.uram * k)

    def as_dict(self):
        return {"LUT": self.lut, "FF": self.ff, "DSP": self.dsp,
                "BRAM36": self.bram36, "URAM": self.uram}


def bind_lane(family, elem_bits):
    """Resources for ONE lane of bind (one element)."""
    if family == "binary":
        return Resources(lut=LUT_PER_XOR * elem_bits)
    if family == "bipolar":
        return Resources(lut=LUT_PER_SIGN_MUL)
    if family == "pow2":
        return Resources(lut=LUT_PER_BIT * elem_bits)            # exponent adder
    if family in ("fixed", "integer"):
        n_dsp = DSP_PER_MUL * math.ceil(elem_bits / DSP_MUL_MAXBITS)
        return Resources(dsp=n_dsp)
    raise ValueError(f"unknown datatype family: {family}")


def add_lane(bits):
    """One accumulate/add lane of the given width (adder + register)."""
    return Resources(lut=LUT_PER_BIT * bits, ff=bits)


def compare_lane(bits):
    """One comparator lane of the given width."""
    return Resources(lut=LUT_PER_BIT * bits)


def mac_lane(family, elem_bits, acc_bits):
    """One multiply-accumulate lane for similarity.

    Binary similarity is XOR + popcount-add (no multiply); other families are a
    real multiply feeding an accumulator.
    """
    if family == "binary":
        return Resources(lut=LUT_PER_XOR + LUT_PER_BIT * acc_bits, ff=acc_bits)
    return bind_lane(family, elem_bits) + add_lane(acc_bits)
