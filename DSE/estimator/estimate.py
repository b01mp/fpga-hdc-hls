"""
estimate.py -- the top-level entry point.

estimate(params) -> metrics dict. `params` is a plain dict bundling the
application parameters and the architecture parameters (a "design point").

NOTE: designpoint.py will later provide a formal dataclass for this; for now we
use a dict so the estimator is fully runnable without it. The schema is exactly
the keys returned by default_params() below.
"""
from .models.device import get_device
from . import compose


def default_params():
    """A representative classification design point (ISOLET-like) at DP=FP=CP=1."""
    return {
        # ---- application parameters ----
        "hv_dim": 10000,
        "num_features": 617,
        "num_prototypes": 26,
        "num_levels": 100,
        "family": "binary",         # binary | bipolar | fixed | integer | pow2
        "elem_bits": 1,
        "acc_bits": 16,
        "proto_bits": 1,
        "sim_bits": 16,
        # ---- architecture parameters ----
        "dp": 1,                    # dimension_parallelism
        "fp": 1,                    # feature_parallelism
        "cp": 1,                    # class_parallelism
        "pipeline_mode": "separate",   # separate | streamed | fused
        "memory_space": "bram",        # bram | uram | hbm | ddr
        "banking_factor": 1,
        "target_fpga": "xczu7ev",
        "clock_ns": 5.0,               # 200 MHz
    }


_APP_KEYS = ("hv_dim", "num_features", "num_prototypes", "num_levels",
             "family", "elem_bits", "acc_bits", "proto_bits", "sim_bits")
_ARCH_KEYS = ("dp", "fp", "cp", "memory_space", "banking_factor")


def _util(value, budget):
    return 100.0 * value / budget if budget else 0.0


def estimate(params):
    """Predict latency / throughput / resources / feasibility for one design point.

    `params` may be a plain dict or a DesignPoint (anything with .to_dict()).
    Unspecified keys fall back to default_params().
    """
    if hasattr(params, "to_dict"):          # accept a DesignPoint transparently
        params = params.to_dict()
    p = {**default_params(), **params}
    dev = get_device(p["target_fpga"])

    app = {k: p[k] for k in _APP_KEYS}
    arch = {k: p[k] for k in _ARCH_KEYS}

    stages = compose.build_classification_infer(app, arch, dev)
    latency_cycles = compose.compose_latency(stages, p["pipeline_mode"])
    per_sample_cycles = compose.bottleneck_cycles(stages, p["pipeline_mode"])
    res = compose.compose_resources(stages)

    clk = p["clock_ns"]
    latency_us = latency_cycles * clk / 1000.0
    throughput_infps = 1e9 / (per_sample_cycles * clk)     # inferences / second

    util = {
        "LUT":    _util(res.lut, dev.lut),
        "FF":     _util(res.ff, dev.ff),
        "DSP":    _util(res.dsp, dev.dsp),
        "BRAM36": _util(res.bram36, dev.bram36),
        "URAM":   _util(res.uram, dev.uram),
    }
    feasible = all(v <= 100.0 for v in util.values())

    return {
        "params": p,
        "latency_cycles": latency_cycles,
        "latency_us": latency_us,
        "throughput_infps": throughput_infps,
        "resources": res.as_dict(),
        "util_pct": util,
        "feasible": feasible,
        "stages": [(s.name, s.cycles) for s in stages],
    }
