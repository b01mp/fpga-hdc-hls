"""Bit-accurate models of the HLS fixed-width integer types.

WHY THIS EXISTS
    The hardware stores hypervector elements in ap_int<W> / ap_uint<W>. To
    predict what a given W costs in ACCURACY, the software model has to reduce
    precision the same way the hardware does. A model that clamps where the
    hardware wraps will show a gentle accuracy slope where the hardware falls
    off a cliff, and the whole Tier-B result would be fiction.

    So: ap_int wraps. It is modular arithmetic, not saturating arithmetic.
    Vitis offers saturation only on ap_fixed with an explicit AP_SAT quantisation
    mode; plain ap_int<W> and ap_uint<W> silently discard the high bits.

THREE DIFFERENT OPERATIONS, DELIBERATELY KEPT APART
    These get lumped together as "reducing precision" and they are not the same
    thing at all:

      wrap      store a value in W bits and let it overflow. What the hardware
                does by default. Catastrophic once the value exceeds the range:
                a large positive count reappears as a large negative one, so the
                stored reference is not merely coarse, it is wrong in the
                direction that maximally corrupts a similarity score.

      saturate  clamp to the representable range. Costs a comparator per store.
                Degrades gracefully at the extremes, but flattens the tails of
                the distribution -- every heavily-agreed dimension becomes
                indistinguishable from every other heavily-agreed dimension.

      scale     divide by a shared factor, round, then store. This is what a
                sensible int8 library actually does. Keeps the SHAPE of the
                distribution and loses resolution uniformly.

    A framework with a single "precision" setting hides which of these it does.
    Reporting all three is the honest version, and the gap between them is a
    result in its own right: it says the width alone does not determine the
    accuracy, the overflow policy does.

VERIFYING AGAINST THE HARDWARE
    self_test() checks the wrap model against hand-computed two's complement
    cases, including the exact one that produced the majority-vote bug in
    include/aggregation/threshold.hpp:

        ap_uint<5> holding 32  ->  0
        ap_int<5>  holding 16  ->  -16

    Run it with:  python3 BioHD/quantize.py
"""
from __future__ import annotations

import torch


# ---------------------------------------------------------------------------
# Representable ranges
# ---------------------------------------------------------------------------
def int_range(bits: int, signed: bool = True) -> tuple[int, int]:
    """Inclusive (min, max) of ap_int<bits> or ap_uint<bits>."""
    if bits < 1:
        raise ValueError("bits must be >= 1")
    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def magnitude_limit(bits: int, signed: bool = True) -> int:
    """Largest magnitude a scaling policy may map onto, at least 1.

    Deliberately uses the POSITIVE limit for signed types. ap_int<W> spans
    -2^(W-1) .. 2^(W-1)-1, so the negative end reaches one further than the
    positive end; scaling to the negative end would produce a positive value
    that is not representable. Clamped to >= 1 because ap_int<1> has a positive
    limit of 0, which would otherwise divide by zero.
    """
    _, hi = int_range(bits, signed)
    return max(hi, 1)


def fits(x: torch.Tensor, bits: int, signed: bool = True) -> bool:
    """True iff every element of x is representable in `bits` bits."""
    lo, hi = int_range(bits, signed)
    return bool((x >= lo).all() and (x <= hi).all())


# ---------------------------------------------------------------------------
# wrap -- what ap_int<W> / ap_uint<W> actually do
# ---------------------------------------------------------------------------
def wrap(x: torch.Tensor, bits: int, signed: bool = True) -> torch.Tensor:
    """Truncate to `bits` bits, two's complement, discarding the high bits.

    This is assignment into an ap_int<bits> / ap_uint<bits>. No saturation, no
    warning, no error -- the value simply reappears elsewhere on the number
    line. Modelled with modular arithmetic rather than bit masking so it is
    correct for negative inputs and for tensors wider than 64 bits' worth of
    intermediate range.
    """
    x = x.to(torch.int64)
    m = 1 << bits
    r = torch.remainder(x, m)                  # 0 .. m-1, correct for negatives
    if not signed:
        return r
    half = 1 << (bits - 1)
    return torch.where(r >= half, r - m, r)


# ---------------------------------------------------------------------------
# saturate -- clamp, as ap_fixed with AP_SAT would
# ---------------------------------------------------------------------------
def saturate(x: torch.Tensor, bits: int, signed: bool = True) -> torch.Tensor:
    """Clamp into the representable range instead of wrapping.

    Not free in hardware: it needs a magnitude comparison and a mux on every
    store. Included because it is what a designer reaches for once they discover
    the wrap, and because the accuracy difference between this and `wrap` is the
    cost of that discovery.
    """
    lo, hi = int_range(bits, signed)
    return torch.clamp(x.to(torch.int64), lo, hi)


# ---------------------------------------------------------------------------
# scale -- reduce resolution uniformly, then store
# ---------------------------------------------------------------------------
def scale_quantize(
    x: torch.Tensor,
    bits: int,
    signed: bool = True,
    scale: float | None = None,
) -> tuple[torch.Tensor, float]:
    """Divide by a shared factor, round to nearest, clamp, and return (q, scale).

    This is what an int8 reference library realistically is: the counts do not
    fit, so they are rescaled once and stored at reduced resolution. The shape
    of the distribution survives; only the resolution drops.

    The scale is chosen so the largest magnitude present lands on the largest
    representable value. Returning it alongside the data matters -- a similarity
    computed against a rescaled reference is off by that constant factor, which
    is harmless for argmax/argmin and for AUC but not for an absolute threshold.
    """
    x = x.to(torch.int64)
    lo, hi = int_range(bits, signed)
    if scale is None:
        peak = int(x.abs().max().item()) if signed else int(x.max().item())
        limit = magnitude_limit(bits, signed)
        scale = 1.0 if peak == 0 else float(peak) / float(limit)
        if scale < 1.0:
            scale = 1.0                       # never upscale; it adds no information
    q = torch.round(x.to(torch.float64) / scale)
    return torch.clamp(q, lo, hi).to(torch.int64), scale


# ---------------------------------------------------------------------------
# sign_binarize -- the ONE-BIT case, which is not an integer truncation
# ---------------------------------------------------------------------------
def sign_binarize(x: torch.Tensor) -> torch.Tensor:
    """Reduce to the two-valued alphabet {-1, +1}. Ties (0) go to +1.

    WHY THIS IS NOT wrap(x, 1).
        A binary hypervector element is a two-valued ALPHABET. In bipolar terms
        its values are -1 and +1, carried in one bit. ap_int<1> is a different
        object: it spans -1..0, because one signed bit has a sign and no
        magnitude. Truncating counts into ap_int<1> keeps the low bit of the
        count, which is parity -- not sign. With an even number of bundled
        patterns every count is even, so the whole reference collapses to zero
        and the reference carries no information at all.

        That is what makes the one-bit point a representation choice rather than
        an overflow policy: all three policies coincide there, because there is
        only one sensible way to keep one bit of a signed quantity.

        The tie convention matches primitives.bundle(mode="binary"), which uses
        `2 * counts >= n` and therefore breaks ties toward 1.
    """
    return torch.where(x >= 0,
                       torch.ones_like(x, dtype=torch.int64),
                       -torch.ones_like(x, dtype=torch.int64))


# ---------------------------------------------------------------------------
# one entry point, so the sweep can treat the policy as data
# ---------------------------------------------------------------------------
POLICIES = ("wrap", "saturate", "scale")


def storage_mode(bits: int, signed: bool = True) -> str:
    """How `bits` bits are actually used -- for labelling results honestly."""
    if signed and bits == 1:
        return "sign{-1,+1}"
    return ("ap_int<%d>" if signed else "ap_uint<%d>") % bits


def apply_policy(
    x: torch.Tensor, bits: int, policy: str, signed: bool = True
) -> torch.Tensor:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")
    # One signed bit is the binary alphabet, not ap_int<1>. Every policy maps to
    # the same thing here; see sign_binarize.
    if signed and bits == 1:
        return sign_binarize(x)
    if policy == "wrap":
        return wrap(x, bits, signed)
    if policy == "saturate":
        return saturate(x, bits, signed)
    q, _ = scale_quantize(x, bits, signed)
    return q


# ---------------------------------------------------------------------------
def self_test() -> int:
    """Check the models against hand-computed two's complement values."""
    failures = 0

    def check(got, want, what):
        nonlocal failures
        if int(got) != int(want):
            print(f"  FAIL {what}: got {int(got)}, want {int(want)}")
            failures += 1

    t = lambda v: torch.tensor([v], dtype=torch.int64)

    # The exact case that produced the majority-vote bug in threshold.hpp:
    # a 5-bit unsigned accumulator asked to hold 2*16.
    check(wrap(t(32), 5, signed=False)[0], 0, "ap_uint<5> <- 32")
    check(wrap(t(16), 5, signed=False)[0], 16, "ap_uint<5> <- 16")
    check(wrap(t(31), 5, signed=False)[0], 31, "ap_uint<5> <- 31")

    # Signed wrap, both directions.
    check(wrap(t(16), 5, signed=True)[0], -16, "ap_int<5> <- 16")
    check(wrap(t(15), 5, signed=True)[0], 15, "ap_int<5> <- 15")
    check(wrap(t(-17), 5, signed=True)[0], 15, "ap_int<5> <- -17")
    check(wrap(t(1024), 11, signed=True)[0], -1024, "ap_int<11> <- 1024")
    check(wrap(t(1024), 12, signed=True)[0], 1024, "ap_int<12> <- 1024 (fits)")

    # Saturation clamps where wrap would fold.
    check(saturate(t(1024), 11, signed=True)[0], 1023, "sat ap_int<11> <- 1024")
    check(saturate(t(-2000), 11, signed=True)[0], -1024, "sat ap_int<11> <- -2000")

    # Ranges.
    lo, hi = int_range(8, signed=True)
    check(lo, -128, "int_range(8, signed).lo")
    check(hi, 127, "int_range(8, signed).hi")
    lo, hi = int_range(8, signed=False)
    check(hi, 255, "int_range(8, unsigned).hi")

    # scale_quantize preserves ordering and lands the peak on the limit.
    x = torch.tensor([-500, -1, 0, 7, 500], dtype=torch.int64)
    q, sc = scale_quantize(x, 8, signed=True)
    if not bool((torch.argsort(x) == torch.argsort(q)).all()):
        print("  FAIL scale_quantize changed the ordering")
        failures += 1
    check(q.abs().max(), 127, "scale_quantize peak lands on 127")

    # The one-bit alphabet: {-1,+1}, ties to +1, and every policy agrees.
    v = torch.tensor([-7, -1, 0, 1, 7], dtype=torch.int64)
    sb = sign_binarize(v)
    for got, want, lbl in zip(sb.tolist(), [-1, -1, 1, 1, 1], ["-7", "-1", "0", "1", "7"]):
        check(got, want, f"sign_binarize({lbl})")
    for pol in POLICIES:
        if not bool((apply_policy(v, 1, pol) == sb).all()):
            print(f"  FAIL policy {pol} disagrees with sign_binarize at 1 bit")
            failures += 1

    # magnitude_limit never returns 0 (that was a division by zero at bits=1).
    check(magnitude_limit(1, True), 1, "magnitude_limit(1, signed)")
    check(magnitude_limit(8, True), 127, "magnitude_limit(8, signed)")
    check(magnitude_limit(8, False), 255, "magnitude_limit(8, unsigned)")
    # scale_quantize must not raise at any width we sweep.
    for b in (1, 2, 4, 8, 16, 32):
        try:
            scale_quantize(torch.tensor([-500, 0, 500], dtype=torch.int64), b, True)
        except Exception as e:              # noqa: BLE001
            print(f"  FAIL scale_quantize raised at bits={b}: {e}")
            failures += 1

    # fits() agrees with the ranges.
    if fits(torch.tensor([128]), 8, signed=True):
        print("  FAIL fits() says 128 fits in ap_int<8>")
        failures += 1
    if not fits(torch.tensor([127]), 8, signed=True):
        print("  FAIL fits() says 127 does not fit in ap_int<8>")
        failures += 1

    print("quantize self_test:", "ALL PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return failures


if __name__ == "__main__":
    raise SystemExit(self_test())
