"""
device.py -- per-target_fpga resource budgets.

These are the CEILINGS the estimator checks a design against. They let us report
utilization % and flag a point as infeasible (doesn't fit). This is also where
the memory hierarchy (Novelty 4) is grounded: how many BRAM/URAM blocks a device
has, and (for off-chip) its HBM/DDR bandwidth.

Numbers are approximate datasheet capacities -- good enough for relative ranking;
calibrate.py can refine anything that matters later.

Capacity units:
  lut, ff, dsp        : counts
  bram36              : number of 36 Kbit block-RAMs
  uram                : number of 288 Kbit UltraRAMs (UltraScale+ only)
  hbm_gbps            : peak off-chip bandwidth (GB/s), 0 if no HBM/DDR modeled
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    name: str
    lut: int
    ff: int
    dsp: int
    bram36: int
    uram: int
    hbm_gbps: float = 0.0
    bram36_bits: int = 36 * 1024      # 36 Kbit per BRAM block
    uram_bits: int = 288 * 1024       # 288 Kbit per URAM block


# Registry of known targets. Add devices here as needed.
DEVICES = {
    # Zynq-7020 -- the license-free part we use for C-sim / calibration.
    "xc7z020": Device("xc7z020", lut=53_200,    ff=106_400,   dsp=220,   bram36=140,  uram=0),
    # Zynq UltraScale+ ZU7EV (ZCU104) -- the edge target.
    "xczu7ev": Device("xczu7ev", lut=230_400,   ff=460_800,   dsp=1_728, bram36=312,  uram=96),
    # Alveo U280 -- datacenter card with HBM (~460 GB/s aggregate).
    "xcu280":  Device("xcu280",  lut=1_303_680, ff=2_607_360, dsp=9_024, bram36=2_016, uram=960, hbm_gbps=460.0),
}


def get_device(name):
    if name not in DEVICES:
        raise KeyError(f"unknown target_fpga '{name}'. known: {list(DEVICES)}")
    return DEVICES[name]
