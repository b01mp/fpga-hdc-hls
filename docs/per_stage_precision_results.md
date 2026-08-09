# Per-Stage Precision — results

**Status:** both tiers measured. Four refinements open (§9).
**Hardware data:** `DSE/synth_results/precision_sweep.csv` (30 points)
**Accuracy data:** `DSE/synth_results/precision_accuracy.csv` (54 points)
**Correctness gate:** `tb/tb_precision.cpp` — ALL PASS
**Target:** U280 (`xcu280-fsvh2892-2L-e`) @ 300 MHz, Vitis HLS 2023.1
**Applications:** image classification, genome search, time-series classification

---

## 1. The question

An HDC pipeline does not carry one kind of number. It carries several, and each
has its own correct width, set by a different property of the workload:

| stage | what it holds | correct width set by |
|---|---|---|
| stored element | the reference library in memory | accuracy requirement |
| bundle accumulator | sum of N hypervectors | **N**, the number bundled |
| similarity score | Hamming distance over D dims | **D**, the hypervector dimension |

N and D are unrelated. A framework with one global datapath width has to pick a
single number for all three. This study measures what that costs.

Prior FPGA-HDC work reports a single precision per design — Hyle sweeps datapath
width uniformly, F5-HD fixes precision per design point, AeneasHDC uses one
datatype. None decomposes the pipeline by stage.

## 2. Terms

**Wrap.** `ap_int<W>` and `ap_uint<W>` are modular. A value too large does not
saturate or raise — it reappears at the other end of the number line, like a
clock passing 12. This is the default and it is silent.

**Saturate.** Clamp to the representable range instead. Costs a comparator per
store; available on `ap_fixed` with `AP_SAT`, not on plain `ap_int`.

**Scale.** Divide by a shared factor, round, then store. Keeps the shape of the
distribution and loses resolution uniformly. What a sensible int8 library does.

**AUC.** Area under the ROC curve — the probability that a stored pattern scores
higher than an unrelated one. 1.0 is perfect separation, 0.5 is a coin flip.

**The rules** (`include/common/hdc_precision.hpp`):

```
bundle_acc_bits<N>     = bits_for(N)            accumulator holds 0..N
hamming_score_bits<D>  = bits_for(D) + 1        score holds 0..D, signed
```

At the applications' own parameters: accumulator 5 / 4 / 3 bits (image / genome
/ time series), score 12 bits at D=1024 and 15 at D=10240.

---

## 3. Method

**Tier A — the intermediates, where narrowing is lossless above a threshold.**
Five configurations per application per D, so the saving can be attributed
rather than asserted:

| config | ACC | SIM | purpose |
|---|---|---|---|
| `wide` | 32 | 32 | what one global datapath width builds |
| `acc_only` | rule | 32 | isolates the accumulator saving |
| `sim_only` | 32 | rule | isolates the score saving |
| `right` | rule | rule | both sized independently — the design |
| `short` | rule | rule−1 | one bit under: the cliff control |

`short` is not a candidate. It is numerically wrong (§4.3) and is synthesized
only to show how little being wrong buys.

**Tier B — the stored element, where narrowing is a genuine trade.** Phase 4's
membership task: bundle P patterns into a reference, then separate stored
patterns from unrelated ones. Sweep stored width × overflow policy.

**On the `wide` baseline being fair.** It is not a strawman. The library's own
generic path uses `acct = ap_int<32>` (`src/top_characterize.cpp`), and the
Python API hardcodes `dtype="int32"` for `bundle` (`python_hdc/api.py`, on
`origin/CPUGPU_baseline`). A design generated through that API *is* `wide`.

---

## 4. Tier A results

### 4.1 Right-sizing is free, and the saving is mostly memory

At D=10240, versus `wide`:

| application | LUT | FF | **BRAM** | latency |
|---|---:|---:|---:|---:|
| image | −12.8% | −21.1% | **64 → 40 (−37.5%)** | identical |
| genome | −6.4% | −4.5% | **56 → 32 (−42.9%)** | identical |
| time series | −7.7% | −5.0% | **56 → 32 (−42.9%)** | identical |

At D=1024 every configuration reports 0 BRAM — the arrays stay in registers and
LUTRAM, and LUT savings are larger (20.9% / 18.9% / 22.1%). The block-RAM saving
exists only once arrays spill, which is why both D values were swept.

**Latency is identical across all five configurations, every application, every
D.** Precision here is a pure area knob with no time cost.

**Reading LUT counts across D is misleading on its own.** `image` at D=10240
uses *fewer* LUTs (4032) than at D=1024 (4386), because the arrays moved out of
LUTRAM into BRAM. LUT and BRAM have to be read together.

### 4.2 Attribution — the accumulator carries it

LUT saving versus `wide`:

| application | D | accumulator | score | both | sum |
|---|---:|---:|---:|---:|---:|
| image | 1024 | 18.60% | 2.28% | 20.88% | 20.88% |
| image | 10240 | 10.71% | 2.11% | 12.82% | 12.82% |
| genome | 1024 | 16.97% | 1.93% | 18.90% | 18.90% |
| genome | 10240 | 5.39% | 1.06% | 6.44% | 6.45% |
| time series | 1024 | 20.04% | 2.05% | 22.09% | 22.09% |
| time series | 10240 | 6.60% | 1.06% | 7.66% | 7.66% |

The savings are **additive** — `both` equals the sum to within rounding in all
six cases, so the two stages do not share logic.

**Honest deflation.** The original code was already at `acc_only` — a
hand-computed `ap_uint<5>` accumulator with an `ap_int<32>` score. Measured
against the code *as it was*, right-sizing the score alone buys 1.1–2.8% LUT and
no BRAM. The large numbers in §4.1 are against `wide`, and the paper must say
which baseline it is quoting.

### 4.3 The cliff

One bit below the rule, from `tb_precision.cpp` case 2:

```
ap_int<32> -> class 1     ap_int<12> -> class 1     ap_int<11> -> class 0
```

At Hamming distance D the 11-bit score wraps negative, the **furthest** reference
becomes the smallest value, and argmin selects it. And the area it saves:

| application | D | right | short | extra saving from being wrong |
|---|---:|---:|---:|---:|
| image | 1024 | 3470 | 3465 | 0.14% |
| image | 10240 | 3515 | 3510 | 0.14% |
| genome | 1024 | 4205 | 4200 | 0.12% |
| genome | 10240 | 7505 | 7500 | 0.07% |
| time series | 1024 | 3795 | 3790 | 0.13% |
| time series | 10240 | 7391 | 7386 | 0.07% |

**There is nothing below the rule.** It is not a good point on a trade-off
curve; it is the cheapest correct point, and everything under it is silently
wrong for free.

---

## 5. Tier B results

### 5.1 One bit is nearly free at realistic load

| P bundled | 1-bit AUC | full-precision AUC | gap |
|---:|---:|---:|---:|
| 50 | 1.0000 | 1.0000 | **0** |
| 500 | 0.9933 | 0.9993 | −0.6% |
| 2000 | 0.8812 | 0.9321 | −5.5% |

Joined with the capacity crossover's storage axis at D=10240:

| P | best width | storage / reference | AUC | vs full precision |
|---:|---|---:|---:|---:|
| 50 | 1 bit | 1.25 KB | 1.0000 | 0 |
| 500 | 1 bit | 1.25 KB | 0.9933 | −0.6% |
| 2000 | 4 bit, `scale` | ~5 KB | 0.9300 | −0.2% |
| — | 32 bit | 40 KB | — | baseline |

**32× less storage for no measurable accuracy loss at light load; 8× for 0.2% at
heavy load.** This strengthens the capacity-crossover result rather than
qualifying it — binary is not a compromise, it is the right default until the
reference is heavily loaded.

### 5.2 The policy matters more than the width

Neither sane policy dominates:

| P | bits | `wrap` | `saturate` | `scale` |
|---:|---:|---:|---:|---:|
| 500 | 2 | 0.4931 | **0.9911** | 0.8884 |
| 500 | 4 | 0.5003 | 0.9962 | **0.9992** |
| 2000 | 2 | 0.4927 | **0.8701** | 0.7870 |
| 2000 | 4 | 0.5025 | 0.8938 | **0.9300** |

The crossover has a clean mechanism. At 2 bits `scale` divides by peak/1, so
nearly everything rounds to zero — signal mean collapses to 25.2 against
saturate's 532.5. At 4 bits with P=2000, `saturate` clips counts of ±174 to ±7,
turning the reference back into a sign function and landing at 0.894, adjacent
to the 1-bit result of 0.881; `scale` keeps the distribution's shape and reaches
0.930.

**`wrap` — the hardware default — sits at chance (0.49–0.53) wherever it
overflows.** Not graceful degradation: a design returning noise.

> **"An int8 library" is not a specification.** Three designs at identical bit
> width span AUC 0.50 to 0.99.

### 5.3 One bit is a representation, not a truncation

`ap_int<1>` spans −1..0 — one signed bit has a sign and no magnitude. Truncating
counts into it keeps the low bit, which is **parity, not sign**; with an even
number of bundled patterns every count is even and the reference collapses to
zero, giving AUC exactly 0.5. A binary element is the two-valued alphabet
{−1,+1} carried in one bit, which is what `bundle(mode="binary")` computes and
what the library's `binary_tag` path builds. The sweep models it as
`sign(counts)`, and all three policies coincide there.

This was a modelling error caught in the first run. Left in, Tier B would have
contradicted Tier A for no real reason.

---

## 6. A defect found by the measurement

`thresh_op(..., binary_tag)` computed the majority vote as:

```cpp
acc_t twice_half = (acc_t)count;
acc_t two_acc    = acc << 1;      // 2*N must fit in acc_t — but acc_t holds only N
```

A bundle accumulator is sized to hold 0..N, so `acc` can reach N and `2*N` does
not fit. When every bundled hypervector agreed on a dimension, the shift wrapped
and the vote returned **0 where it must return 1**.

| application | N | `acc_t` | holds `2N`? |
|---|---:|---|---|
| image classification | 16 | `ap_uint<5>` (0..31) | **no — 32** |
| genome | 8 | `ap_uint<4>` (0..15) | **no — 16** |
| time series | 6 | `ap_uint<4>` (0..15) | yes — 12 |

Two of three applications were affected. The failure needs unanimity on a
dimension — roughly 3 in 100,000 per dimension at N=16 with random inputs — so it
survives casual testing and corrupts a bit of the query hypervector when it
fires. Time series escaped only because its constant was the loose one.

Fixed by widening the comparands rather than the accumulator: requiring callers
to carry `bits_for(N)+1` would spend a flip-flop on every one of D dimensions to
accommodate one comparison.

**The two fixes were not independent.** Tightening time series to the derived
`ap_uint<3>` would have introduced the bug there too (`6<<1 = 12` wraps in 3
bits). The width derivation could not have been applied safely without fixing
`thresh_op` first.

---

## 7. What is measured and what is modelled

| claim | basis |
|---|---|
| Tier A areas and latencies | csynth estimate, U280 |
| right-sized == 32-bit, bit-identical | **measured** — csim, 40 random trials × 3 applications |
| one bit short mispredicts | **measured** — csim, deterministic worst case |
| majority-vote fix | **measured** — csim regression, all three applications |
| Tier B AUC | software model, bit-accurate to `ap_int` wrap semantics |
| storage per reference | from the capacity crossover, Vivado-confirmed |

**Open risk.** Tier A is pre-place-and-route. In the capacity study csynth
under-reported BRAM by roughly 32× on a large array, and BRAM is the headline
number here — so the 37–43% figure is the one most exposed. A Vivado run on the
`wide` and `right` points of one application would settle it, using the existing
`scripts/confirm_capacity_cliff.tcl` machinery.

---

## 8. The claims, and what backs each

| claim | evidence | strength |
|---|---|---|
| per-stage sizing saves 37–43% BRAM vs one global width | `precision_sweep.csv`, 3 applications | strong; csynth only |
| …at identical latency and bit-identical output | csim + sweep | strong |
| the boundary is a cliff, not a knee (0.07–0.14%) | `precision_sweep.csv` + csim case 2 | **strongest single result** |
| the accumulator holds the area, the score holds the risk | attribution table §4.2 | strong |
| 1 bit costs ≤0.6% AUC at P≤500, for 32× storage | `precision_accuracy.csv` | strong; single seed |
| overflow policy matters more than width | §5.2 | strong; single seed |
| per-primitive measurement catches real defects | §6 | one instance, but concrete |

---

## 9. Open items

**Single seed.** `SEED = 0`, no error bars. Differences like 0.9911 vs 0.9884
are not defensible from one run. Three to five seeds is minutes of compute.

**AUC is generous.** It compresses differences, and 0.88 can still be unusable
for retrieval. `search.py` already computes TPR at low FPR — reporting
`TPR@FPR≤0.05` beside AUC is the operationally honest number and is already
written.

**The `scale` factor is data-derived.** In hardware it is fixed at design time,
so the current `scale` numbers are a mild best case. Either fix the scale or say
so.

**The two tiers are not yet combined.** Tier B models a full-precision query and
an unbounded accumulator — the stage Tier A bounds. The real design has both,
and neither study alone describes it.

---

## 10. Figures and tables to produce

**Figure A — the cliff (Tier A headline).**
Grouped bars, one group per application at D=10240, bars = `wide`, `right`,
`short`, height = BRAM18K. Annotate `short` with "numerically wrong". The story
is that `right` is much shorter than `wide` and `short` is indistinguishable
from `right`.
Source: `precision_sweep.csv` → `app`, `config`, `BRAM18K`, filter `D == 10240`.

**Figure B — attribution.**
Stacked horizontal bars, one per (application, D): accumulator contribution and
score contribution to the LUT saving, summing to the total.
Source: `precision_sweep.csv` → `LUT_vs_wide` for `acc_only`, `sim_only`,
`right`.

**Figure C — accuracy vs width, by policy (Tier B headline).**
Three panels (P = 50, 500, 2000), x = bits per stored element on a log₂ axis,
y = AUC, one line per policy, horizontal reference line at the full-precision
AUC. `wrap` flatlines near 0.5 wherever `overflowed == 1`; the other two rise and
converge. Already generated at
`BioHD/experiments/output/phase7_precision_accuracy.png`.
Source: `precision_accuracy.csv` → `P`, `bits`, `policy`, `auc`, `overflowed`.

**Figure D — accuracy vs area Pareto (the one that ties both studies).**
x = storage per reference in KB (log), y = AUC, one series per P, points at
1/4/8/32 bits, best policy at each width. Mark the 32-bit point and draw the
horizontal distance to the 1-bit point — that gap is the headline.
Source: `precision_accuracy.csv` joined to `capacity_sweep.csv` on
bits-per-element. **Not yet written** — this is B3.

**Table 1 — Tier A, five configurations × three applications × two D.**
Source: `precision_sweep.csv` directly. Columns: application, D, config, latency,
LUT, LUT-%, FF, FF-%, BRAM, BRAM-%. Footnote that `short` is numerically wrong.

**Table 2 — the width rules.**
application, N, D, accumulator bits, score bits, and the 32-bit baseline
alongside. Small, and it makes the "different quantities" point without prose.

**Do not plot latency.** It is identical everywhere; a flat chart says nothing
that one sentence does not say better.

---

## 11. Suggested paper structure

| section | content | source |
|---|---|---|
| motivation | pipelines carry several kinds of number; one width cannot serve all | §1, §2, Table 2 |
| method | the rules, the five configurations, why `wide` is fair | §3 |
| result 1: cost | 37–43% BRAM, identical latency, bit-identical | §4.1, Figure A |
| result 2: attribution | accumulator holds the area, score holds the risk | §4.2, Figure B |
| result 3: the cliff | 0.14% cheaper and wrong | §4.3 |
| result 4: accuracy | 1 bit ≈ free; policy > width | §5, Figure C |
| synthesis | the accuracy/area Pareto | Figure D |
| methodology note | per-primitive measurement caught a real defect | §6, **one sentence, no numbers** |

The defect belongs in the methodology argument, not the results. It justifies why
the measurement is worth doing; it is not itself a contribution.

---

## 12. Reproduction

```bash
# Tier A -- yangzi
source /tools/Xilinx/Vitis/2023.1/settings64.sh
cd ~/fpga-hdc-hls
vitis_hls -f scripts/csim_precision.tcl          # GATE -- must print ALL PASS
nohup vitis_hls -f scripts/sweep_precision.tcl > precision.log 2>&1 &
python3 DSE/collect_precision.py                 # -> precision_sweep.csv
```

```powershell
# Tier B -- laptop, needs the BioHD venv
cd C:\USC\fpga-hdc-hls\BioHD
.\.venv\Scripts\python.exe quantize.py           # GATE -- must print ALL PASS
.\.venv\Scripts\python.exe experiments\phase7_precision_accuracy.py
```

Overridable: `HDC_PREC_D` (D list), `HDC_PART` / `HDC_PERIOD` / `HDC_TAG`
(`scripts/target.tcl`), and `P_VALUES` / `BIT_WIDTHS` / `SEED` at the top of
`phase7_precision_accuracy.py`.
