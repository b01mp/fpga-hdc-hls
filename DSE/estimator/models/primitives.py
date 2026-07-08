"""
primitives.py -- per-primitive cost models.

Each cost_* function mirrors a library primitive 1:1 and returns
    (latency_cycles, Resources)
for ONE invocation. Latency assumes a pipelined loop (II=1), so a D-length
elementwise pass with DP parallel lanes takes ceil(D/DP) cycles. Resources are
the per-lane cost (from datatypes.py) replicated by the parallelism factor.

These formulas must match what the HLS pragmas actually produce -- e.g. bind's
`ceil(D/DP)` mirrors `#pragma HLS UNROLL factor=DP` on the D-loop.
"""
import math
from .datatypes import Resources, bind_lane, add_lane, compare_lane, mac_lane


def ceil_div(a, b):
    return -(-a // b)


# ---- Encoding -------------------------------------------------------------
def cost_bind(D, DP, family, elem_bits):
    """(a,b)->out elementwise. ceil(D/DP) cycles; DP bind lanes."""
    cycles = ceil_div(D, DP)
    res = bind_lane(family, elem_bits).scale(DP)
    return cycles, res


def cost_quantize(FP, feat_bits=32):
    """Scalar value -> level index, FP features in parallel. A few-cycle pipeline;
    dominated by the D-vector ops downstream, so latency is a small constant."""
    QUANT_PIPE = 6                       # pipeline depth of the bucketize
    LUT_PER_QUANT = 40                   # a float compare/scale ~ tens of LUTs
    return QUANT_PIPE, Resources(lut=LUT_PER_QUANT * FP)


# ---- Aggregation ----------------------------------------------------------
def cost_bundle(D, DP, acc_bits):
    """Accumulate one HV into the running accumulator. ceil(D/DP) cycles."""
    cycles = ceil_div(D, DP)
    res = add_lane(acc_bits).scale(DP)
    return cycles, res


def cost_threshold(D, DP, acc_bits):
    """Collapse accumulator -> HV (majority/sign/passthrough). ceil(D/DP) cycles."""
    cycles = ceil_div(D, DP)
    res = compare_lane(acc_bits).scale(DP)
    return cycles, res


# ---- Memory ---------------------------------------------------------------
def cost_gather(D, DP):
    """Indexed read of one D-vector from a codebook, DP elements/cycle."""
    cycles = ceil_div(D, DP)
    res = Resources(lut=DP)              # addressing / muxing
    return cycles, res


# ---- Search ---------------------------------------------------------------
def cost_similarity(D, K, DP, CP, family, elem_bits, sim_bits):
    """Compare query to K prototypes (CP class-parallel, DP dim-parallel)."""
    cycles = ceil_div(K, CP) * ceil_div(D, DP) + math.ceil(math.log2(max(D, 2)))
    lane = mac_lane(family, elem_bits, sim_bits)
    res = lane.scale(CP * DP)
    res = res + compare_lane(sim_bits).scale(CP)     # per-class argmin/argmax
    return cycles, res


# ---- Memory footprint (codebooks / prototypes) ----------------------------
def mem_blocks(bits, memory_space, banking, device):
    """On-chip block count for a tensor. Off-chip (hbm/ddr) uses no on-chip blocks.

    Banking (array partitioning) splits a tensor into >=`banking` physical banks,
    so it can never use fewer than `banking` blocks.
    """
    if memory_space == "bram":
        base = ceil_div(bits, device.bram36_bits)
        return Resources(bram36=max(base, banking))
    if memory_space == "uram":
        base = ceil_div(bits, device.uram_bits)
        return Resources(uram=max(base, banking))
    # hbm / ddr : off-chip -- no on-chip blocks (bandwidth handled elsewhere)
    return Resources()
