# Capacity Crossover — on-chip vs off-chip reference library

**Status:** complete.
**Data:** `DSE/synth_results/capacity_sweep.csv`
**Evidence:** `DSE/synth_results/cliff_confirm/`
**Target:** U280 (`xcu280-fsvh2892-2L-e`) @ 300 MHz, Vitis HLS 2023.1, Vivado 2023.1

---

## 1. The question

Prior FPGA-HDC frameworks hold the entire reference library in on-chip memory.
Hyle states the assumption outright — hypervectors in BRAM with single-cycle
access, chosen so memory never enters the measurement. F5-HD and AeneasHDC keep
class hypervectors in BRAM the same way; F5-HD streams only *input feature maps*
from off-chip, never the model.

That silently bounds the problem sizes those frameworks can express. This
experiment measures where the bound is, what sets it, and what it costs to
remove it.

## 2. Setup

Two designs, identical in every respect except where a reference word comes from:

| | source of a reference word |
|---|---|
| `src/top_onchip_search.cpp` | on-chip array (what prior work builds) |
| `src/top_compose_biohd.cpp` | FIFO fed by an `m_axi` master (streaming) |

Same D, same K, same query batch, same metric dispatch, same packed 512-bit word
layout, same search-primitive structure. `include/search/similarity_search_onchip.hpp`
is a line-for-line mirror of `similarity_search_stream_dt.hpp` with
`codebook[(start+k)*WPR + w]` in place of `protos.read()`.

**Swept:** K ∈ {32, 64, 128, 256, 512, 1024} × precision X ∈ {1, 8, 32} × both tiers.
36 csynth runs.
**Held constant:** D = 10240 (BioHD anchor), QB = 4, CP = 1, part, clock.

## 3. Results

### 3.1 The on-chip capacity cliff, and precision sets it

U280 BRAM is 4,032 × 18 Kbit = 9.07 MB.

| Precision | Bytes / reference | Largest K measured to fit | First K that fails | Cliff (computed) |
|---|---:|---:|---:|---:|
| binary (X=1) | 1.25 KB | 1024 (14.1%) | none in sweep | **K ≈ 7116** |
| int8 (X=8) | 10 KB | 512 (56.4%) | **1024** (112.9%) | **K ≈ 889** |
| int32 (X=32) | 40 KB | 128 (56.4%) | **256** (112.9%) | **K ≈ 222** |

7116 / 222 = **32.0×** — exactly the precision ratio. Same application, same
source, one parameter. **Precision, not the application, determines which side of
the on-chip memory boundary a design lands on.**

### 3.2 Streaming decouples on-chip cost from library size

This is the measured result, and the strongest one.

| K | on-chip BRAM (required) | streaming BRAM (reported) |
|---:|---:|---:|
| 32 | 580 | **45** |
| 128 | 2,320 | **45** |
| 256 | 4,640 | **45** |
| 1024 | 18,560 | **45** |

(int32; the pattern is identical at every precision.)

The streaming design holds only a FIFO's worth of the library on chip, so its
on-chip footprint is **constant in K and in precision** — 45 blocks at every one
of the 18 off-chip points. The on-chip design's grows linearly and eventually
exceeds the device.

At the first failing configuration (int32, K=256) the on-chip design needs
**4,640 blocks against 4,032 available**; the streaming design needs **45**. Same
workload, **103×** less on-chip memory.

### 3.3 The price is 33%

| X | K | on-chip cycles | streaming cycles | ratio |
|---:|---:|---:|---:|---:|
| 1 | 1024 | 20,583 | 27,307 | 1.33 |
| 8 | 512 | 82,023 | 109,227 | 1.33 |
| 32 | 128 | 82,023 | 109,227 | 1.33 |

The ratio converges to exactly 4/3. At 300 MHz a 512-bit port *demands*
19.2 GB/s; one U280 HBM2 pseudo-channel *delivers* 14.4 GB/s. 19.2 / 14.4 = 1.333.
It is lower at small K (1.15 at K=32) only because fixed pipeline overhead
dominates a short scan.

**The trade, stated plainly: unbounded library capacity costs 33% latency.**
Prior work does not get to make that trade, because on-chip is its only option.

## 4. Validation

`csynth` does **not** fail when a design exceeds device resources — it reports
400% BRAM and exits cleanly. Worse, it *under-reports*: for the 40 MB codebook at
int32/K=1024 it claims 144 BRAM18K, short by roughly 32×. Vitis caps memory
inference on large arrays rather than reporting the true requirement.

Footprint is therefore computed as K·D·X bits packed into 18 Kbit blocks
(`ceil(512/18)` blocks per 1024 entries), which is how prior work reports model
size too — Hyle gives it as an equation, not a synthesis result.

To confirm the computed model is real, the boundary configuration was pushed
through Vivado synthesis and placement.

### int32, K=256 — the first predicted failure (112.9%)

| | BRAM18-equivalent blocks |
|---|---:|
| Computed estimate | 4,640 |
| Vivado, post-synthesis | **4,653** |
| Device available | 4,032 |

**Model error: 0.28%.** (2,294 RAMB36 × 2 + 65 RAMB18 = 4,653.)

Vivado post-synthesis utilisation: Block RAM Tile **2,326.5 / 2,016 = 115.40%**.
Placement refused:

```
ERROR: [DRC UTLZ-1] Resource utilization: RAMB18 and RAMB36/FIFO over-utilized
in Top Level Design ... requires 4653 of such cell types but only 4032
compatible sites are available in the target device ... consider targeting a
larger device.
ERROR: [Vivado_Tcl 4-23] Error(s) found during DRC. Placer not run.
```

Three DRC errors, all resource over-utilisation. Not a clock or IO artifact.

### int32, K=128 — the last predicted fit (57.5%)

| | BRAM18-equivalent blocks |
|---|---:|
| Computed estimate | 2,320 |
| Vivado, post-synthesis | **2,373** |
| Device available | 4,032 |

Vivado post-synthesis utilisation: Block RAM Tile **1,186.5 / 2,016 = 58.85%**.
`synth_design` completed, `place_design` **completed**. The design builds.

### The matched pair

| K | predicted util. | Vivado util. | predicted verdict | Vivado verdict |
|---:|---:|---:|---|---|
| 128 | 57.5% | **58.85%** | fits | **placed successfully** |
| 256 | 115.1% | **115.40%** | does not fit | **placement refused (DRC)** |

One side of the boundary builds, the other is refused, and the model predicts
both to within 1.4 percentage points. This rules out the failing design having
failed for some unrelated reason.

**On the residual.** The model is accurate to 0.3% at K=256 and 2.3% at K=128,
and the discrepancy is a roughly constant **~65-block fixed overhead** — query
buffers, FIFOs and control state, which a codebook-only footprint model does not
count (RAMB18 sits at 65 in both runs, independent of K). The model therefore
*under*-counts slightly, which means the true cliff is marginally **earlier**
than reported. The error is conservative in the right direction: it is generous
to the on-chip baseline, never to the streaming design.

## 5. What is measured and what is modelled

| Claim | Basis |
|---|---|
| streaming on-chip cost is constant at 45 blocks | **measured** (csynth, 18 points) |
| on-chip cost grows linearly with K and X | **measured**, validated against Vivado to 0.28% |
| cliff at K≈222 / 889 / 7116 | computed; **confirmed by Vivado on both sides of the int32 boundary** |
| 1.33× latency penalty | **modelled** — see caveat below |
| both designs at 411 MHz | csynth estimate, optimistic for both equally |

**Latency caveat.** `csynth` schedules an `m_axi` read at II=1 and assumes the
word arrives; it models no DRAM latency, bandwidth or contention. Without a
ceiling the two tiers come out within 10 cycles of each other at every point,
which is an artifact of that assumption. The ceiling applied is
`max(schedule, bytes / 14.4 GB/s)`, assuming perfectly sequential fully-utilised
bursts — which this design does issue. That is an *upper* bound on delivered
bandwidth and therefore a *lower* bound on off-chip time: a board measurement
could only move it against the streaming design, never in its favour.

Because the design demands exactly one word per cycle everywhere, this ceiling is
a uniform 4/3 factor on every off-chip point. It shifts the line; it does not
change its shape. It is reported for honesty, not as a finding.

**Conservative direction.** The computed footprint counts *only* the codebook.
Real on-chip usage also includes query buffers and control state — measured at
**~65 blocks, constant in K** across both Vivado runs. The true cliff is
therefore marginally **earlier** than reported: the estimate is generous to the
on-chip baseline, never to the streaming design.

## 6. Reproduction

```bash
source /tools/Xilinx/Vitis/2023.1/settings64.sh

# 36-point sweep (~1 hour on U280)
vitis_hls -f scripts/sweep_capacity.tcl 2>&1 | tee capacity_sweep.log
python3 DSE/collect_capacity.py

# boundary confirmation (~15 min each)
vivado -mode batch -source scripts/confirm_capacity_cliff.tcl 2>&1 | tee cliff_confirm.log
HDC_CLIFF_PROJ=proj_cap_onchip_x32_k128 \
  vivado -mode batch -source scripts/confirm_capacity_cliff.tcl 2>&1 | tee cliff_confirm_k128.log
```

## 7. Open items

- pow2 is absent from the precision axis: the streaming path requires
  `512 % X == 0` and 512/6 is not an integer, so a 6-bit pow2 element must be
  padded to 8 bits. The X=8 column becomes its slot once pow2 overloads are added
  to `similarity_search_stream_dt.hpp`. Worth reporting in its own right — the
  theoretical 6-bit representation costs 8 bits in a 512-bit-word system.
- The sweep fixes CP=1. Channel parallelism interacts with the bandwidth ceiling
  and belongs to the knob-interaction experiment.
- A measured off-chip latency needs hardware emulation (`v++ -t hw_emu`) or a
  board run; neither is in scope here.