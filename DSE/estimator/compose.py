"""
compose.py -- stitch per-primitive costs into an application pipeline.

An app is a dataflow graph of primitives. This module builds the stages of a
given app and composes their costs according to `pipeline_mode`:

  separate : stages run one after another   -> latency = SUM of stage cycles
  streamed : stages overlap (dataflow/FIFOs) -> latency ~ MAX stage + small fill,
             and steady-state throughput is set by the SLOWEST stage
  fused    : treated like streamed for this first model

Resources are summed across all instantiated stages (the hardware coexists).
"""
from dataclasses import dataclass
from .models.datatypes import Resources
from .models import primitives as P


@dataclass
class Stage:
    name: str
    cycles: int
    res: Resources


def build_classification_infer(app, arch, device):
    """Stages of the classification INFER pipeline:

        encode = ceil(F/FP) x ( quantize -> gather(level) -> bind(base) -> bundle )
                 then threshold(acc) -> query HV
        infer  = encode -> similarity_search over K prototypes
    """
    D = app["hv_dim"]; F = app["num_features"]; K = app["num_prototypes"]; L = app["num_levels"]
    fam = app["family"]; eb = app["elem_bits"]; ab = app["acc_bits"]
    pb = app["proto_bits"]; sb = app["sim_bits"]
    DP = arch["dp"]; FP = arch["fp"]; CP = arch["cp"]
    ms = arch["memory_space"]; bank = arch["banking_factor"]

    stages = []

    # --- encode: per-feature vector work, repeated ceil(F/FP) times ---
    q_cyc, q_res = P.cost_quantize(FP)
    g_cyc, g_res = P.cost_gather(D, DP)
    b_cyc, b_res = P.cost_bind(D, DP, fam, eb)
    u_cyc, u_res = P.cost_bundle(D, DP, ab)

    feature_passes = P.ceil_div(F, FP)
    per_feature_cycles = q_cyc + g_cyc + b_cyc + u_cyc      # chained within a feature
    encode_cycles = feature_passes * per_feature_cycles
    # the datapath is instantiated once, replicated FP-fold for feature parallelism
    encode_res = (q_res + g_res + b_res + u_res).scale(FP)
    stages.append(Stage("encode", encode_cycles, encode_res))

    # --- threshold: accumulator -> query HV ---
    t_cyc, t_res = P.cost_threshold(D, DP, ab)
    stages.append(Stage("threshold", t_cyc, t_res))

    # --- similarity search over K prototypes ---
    s_cyc, s_res = P.cost_similarity(D, K, DP, CP, fam, eb, sb)
    stages.append(Stage("similarity", s_cyc, s_res))

    # --- memories (no latency stage; resources only) ---
    mem = (P.mem_blocks(F * D * eb, ms, bank, device)      # base codebook
           + P.mem_blocks(L * D * eb, ms, bank, device)    # level codebook
           + P.mem_blocks(K * D * pb, ms, bank, device))   # prototypes
    stages.append(Stage("memory", 0, mem))

    return stages


def compose_latency(stages, pipeline_mode):
    """End-to-end latency (cycles) for ONE sample."""
    compute = [s.cycles for s in stages if s.cycles > 0]
    if not compute:
        return 0
    if pipeline_mode in ("streamed", "fused"):
        return max(compute) + int(0.1 * sum(compute))      # slowest stage + fill
    return sum(compute)                                     # separate: sequential


def bottleneck_cycles(stages, pipeline_mode):
    """Cycles-per-sample in steady state (drives throughput)."""
    compute = [s.cycles for s in stages if s.cycles > 0]
    if not compute:
        return 1
    if pipeline_mode in ("streamed", "fused"):
        return max(compute)                                # throughput = slowest stage
    return sum(compute)                                    # separate: one at a time


def compose_resources(stages):
    total = Resources()
    for s in stages:
        total = total + s.res
    return total
