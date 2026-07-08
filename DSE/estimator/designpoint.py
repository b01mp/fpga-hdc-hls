"""
designpoint.py -- the formal INPUT object for the estimator.

A DesignPoint bundles the application parameters and the architecture parameters
that define ONE point in the DSE search space, and validates them (legality
checks: dp in range and divides hv_dim, memory_space supported by the device,
etc.).

Callers (the CLI, sweep.py, or Haoyang's DSE) can build a DesignPoint and hand it
to estimate(). estimate() also still accepts a plain dict, so this is an
optional, safer front-end -- not a required step. You never "run" this file; you
import it and construct objects.
"""
from dataclasses import dataclass, asdict, fields
from .models.datatypes import FAMILIES
from .models.device import DEVICES, get_device

PIPELINE_MODES = ("separate", "streamed", "fused")
MEMORY_SPACES = ("bram", "uram", "hbm", "ddr")


@dataclass
class DesignPoint:
    # ---- application parameters ----
    hv_dim: int = 10000
    num_features: int = 617
    num_prototypes: int = 26
    num_levels: int = 100
    family: str = "binary"          # binary | bipolar | fixed | integer | pow2
    elem_bits: int = 1
    acc_bits: int = 16
    proto_bits: int = 1
    sim_bits: int = 16
    # ---- architecture parameters ----
    dp: int = 1                     # dimension_parallelism
    fp: int = 1                     # feature_parallelism
    cp: int = 1                     # class_parallelism
    pipeline_mode: str = "separate"    # separate | streamed | fused
    memory_space: str = "bram"         # bram | uram | hbm | ddr
    banking_factor: int = 1
    target_fpga: str = "xczu7ev"
    clock_ns: float = 5.0

    # ------------------------------------------------------------------ #
    # conversions
    # ------------------------------------------------------------------ #
    def to_dict(self):
        """Plain-dict form -- exactly the schema estimate() consumes."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        """Build from a dict, ignoring any keys that aren't fields."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def default(cls, **overrides):
        """A default point with the given keyword overrides applied."""
        return cls.from_dict({**cls().to_dict(), **overrides})

    # ------------------------------------------------------------------ #
    # validation
    # ------------------------------------------------------------------ #
    def validate(self):
        """Return {'errors': [...], 'warnings': [...]}.

        errors   = illegal (out of range, unknown enum, unsupported on device)
        warnings = legal but suboptimal (e.g. parallelism that divides unevenly)
        """
        errors, warnings = [], []

        # -- enums --
        if self.family not in FAMILIES:
            errors.append(f"family '{self.family}' not in {FAMILIES}")
        if self.pipeline_mode not in PIPELINE_MODES:
            errors.append(f"pipeline_mode '{self.pipeline_mode}' not in {PIPELINE_MODES}")
        if self.memory_space not in MEMORY_SPACES:
            errors.append(f"memory_space '{self.memory_space}' not in {MEMORY_SPACES}")
        if self.target_fpga not in DEVICES:
            errors.append(f"target_fpga '{self.target_fpga}' not in {list(DEVICES)}")

        # -- positive sizes / widths --
        for name in ("hv_dim", "num_features", "num_prototypes", "num_levels",
                     "elem_bits", "acc_bits", "proto_bits", "sim_bits"):
            if getattr(self, name) < 1:
                errors.append(f"{name} must be >= 1 (got {getattr(self, name)})")
        if self.clock_ns <= 0:
            errors.append(f"clock_ns must be > 0 (got {self.clock_ns})")

        # -- parallelism ranges (+ divisibility as a warning) --
        if not (1 <= self.dp <= self.hv_dim):
            errors.append(f"dp must be in [1, hv_dim={self.hv_dim}] (got {self.dp})")
        elif self.hv_dim % self.dp != 0:
            warnings.append(f"dp={self.dp} does not divide hv_dim={self.hv_dim} (uneven unroll)")

        if not (1 <= self.fp <= self.num_features):
            errors.append(f"fp must be in [1, num_features={self.num_features}] (got {self.fp})")
        elif self.num_features % self.fp != 0:
            warnings.append(f"fp={self.fp} does not divide num_features={self.num_features}")

        if not (1 <= self.cp <= self.num_prototypes):
            errors.append(f"cp must be in [1, num_prototypes={self.num_prototypes}] (got {self.cp})")

        if not (1 <= self.banking_factor <= self.hv_dim):
            errors.append(f"banking_factor must be in [1, hv_dim] (got {self.banking_factor})")

        # -- device gating for the memory tier --
        if self.target_fpga in DEVICES and self.memory_space in MEMORY_SPACES:
            dev = get_device(self.target_fpga)
            if self.memory_space == "uram" and dev.uram == 0:
                errors.append(f"memory_space 'uram' but {dev.name} has no URAM")
            if self.memory_space in ("hbm", "ddr") and dev.hbm_gbps == 0:
                errors.append(f"memory_space '{self.memory_space}' but {dev.name} has no off-chip "
                              f"bandwidth modeled")

        return {"errors": errors, "warnings": warnings}

    def is_legal(self):
        """True if the point has no hard errors (warnings are allowed)."""
        return not self.validate()["errors"]
