# Generation & On-the-Fly Generation — Deferred Implementation Plan

**Status:** NOT STARTED. Deferred until the paper draft is complete.
**Written:** 2026-07-17, during the architecture-section drafting.

## Why this file exists

The paper's Architecture Design section (subsections *Generation* and *On-the-Fly
Generation*) describes generation behavior that **the library does not currently
implement**. The text was written first, deliberately, so the implementation has a
specification to build against. This file is that specification.

Until these changes land, the two subsections describe *intent*, not code. Nothing
from them may appear in the evaluation section.

The on-the-fly technique is adapted from:

> Schmuck, Benini, Rahimi. *Hardware Optimizations of Dense Binary Hyperdimensional
> Computing: Rematerialization of Hypervectors, Binarized Bundling, and
> Combinational Associative Memory.* ACM JETC 15(4), 2019. doi:10.1145/3314326

**Attribution boundary (keep this sharp):** the binary XOR manipulator and the
rule-30 cellular automaton are Schmuck's. Ours are (a) the bipolar sign decode,
(b) the arithmetic-family interpolation, and (c) making `materialize` a searchable
architecture parameter alongside memory tier. Do not blur this.

## Current state (verified 2026-07-17)

| File | Reality |
| --- | --- |
| `include/generation/random_hv.hpp` | host-side `std::mt19937`; draws `bit(0,1)` and casts to `elem_t` |
| `include/generation/gen_levels.hpp` | host-side; flip schedule via `std::shuffle`; binary-valued, cast to `elem_t` |
| `include/generation/rematerialize.hpp` | host-side; seeks row `k` by replaying the RNG `index*D` times |
| characterization | **none** — generation has never been synthesized or characterized |
| `materialize` knob | **does not exist** anywhere |

None of the three is synthesizable. Generation carries **no HLS pragmas at all**,
so it opts out of the `DP` / cyclic-partition / `II=1` idiom every other primitive
follows.

---

## A. Bug fixes — materialized generation is not actually datatype-parametric

### A1. `random_hv.hpp` — tag-dispatch the draw  *(~30 min)*

**This is a silent bug, not just a paper gap. Fix it regardless of the paper.**

The function is templated on `elem_t` but always draws `bit(0,1)` and casts, so
`bipolar_t` receives **{0, 1} instead of {-1, +1}**. A bipolar experiment would run
and look plausible while having no negative values in its codebook.

Add a `typename Family = binary_tag` template parameter and a per-family draw
helper, mirroring the `bind_op` pattern in `encoding/bind.hpp`:

```
draw_elem(rng, binary_tag)  -> Bernoulli {0,1}
draw_elem(rng, bipolar_tag) -> Rademacher {-1,+1}
draw_elem(rng, fixed_tag)   -> uniform over representable range
draw_elem(rng, integer_tag) -> uniform over representable range
draw_elem(rng, pow2_tag)    -> uniform over exponent range
```

### A2. `gen_levels.hpp` — per-family level construction  *(~2 hr)*

Same defect (`cur[i] ^= 1` then cast). Needs a `Family` tag and three paths:

- **binary** — flip schedule as-is
- **bipolar** — flip schedule + {0,1} -> {-1,+1} decode
- **fixed / integer / pow2** — **interpolation between two endpoint hypervectors**.
  Bit-flipping has no meaning here; graded *value* distance replaces graded Hamming
  distance. This is genuinely new code.

Only required if the paper claims non-binary on-the-fly generation.

---

## B. The `materialize` knob — does not exist

### B1. Uniform codebook-read interface  *(~1 hr)*

The paper claims fetch and generate are **swappable variants of one node**. They
are not — the signatures differ:

```cpp
gather<elem_t,N,D,DP>(codebook[N][D], index, out[D])   // takes an array
rematerialize<elem_t,D>(index, out[D], seed)           // takes a seed
```

Add a dispatching wrapper (e.g. `codebook_read<..., Materialize>`) tag-dispatched
on `store_tag` / `regen_tag`, so a consumer's call site is identical either way.

**This is the change that makes the entire framing true rather than aspirational.**
Without it, "two variants of one interface" is a claim about nothing.

---

## C. The generators — nothing here is synthesizable today

### C1. Level manipulator — new file  *(~2-3 hr)*

Replace `std::mt19937` with a synthesizable network:

- `S0` and the step-assignment map as **compile-time constants** so they synthesize
  to wiring and LUT constants, not memory
- s-hot expansion (`h_s[m] = 1 iff m <= s`) via an `L x L` table
- one XOR per flipped dimension (`D/2` gates total)
- `#pragma HLS PIPELINE II=1` + `#pragma HLS UNROLL factor=DP` on the D loop, so it
  finally joins the library's common idiom (`DP/2` gates, `ceil(D/DP)` cycles)

> **KEY IMPLEMENTATION INSIGHT — do not miss this.**
> The connectivity matrix `M` **is** the `gen_levels` permutation. Dimension
> `perm[p]` flips at step `1 + p/per_step`, so:
>
> ```
> S_s[n] = S0[n] ^ (phi(n) <= s)      where phi comes straight from perm
> ```
>
> **One build-time artifact serves both paths**: the materialized path writes a
> codebook with it, the generated path routes with it. This is what makes the
> paper's "reproduces the flip schedule exactly" claim true *by construction* — you
> are not designing anything new, only re-expressing what `gen_levels` already
> computes. Build C1 by refactoring `gen_levels`, not from scratch.

Schmuck's s-hot-LUT formulation (`L x L` LUT + routing + `D/2` XORs) is cheaper
than the naive alternative of `D` comparators (each `log2(L)` bits wide), because
the comparison is amortized into the LUT and the fan-out becomes routing.

### C2. Item automaton — new file  *(~2 hr)*

One-dimensional cellular automaton, rule 30, `D` cells:

```
next[i] = cur[(i-1+D) % D] ^ ( cur[i] | cur[(i+1) % D] )
```

- `D` registers of state; item `k` is the state after `k` update steps
- `UNROLL factor=DP` -> `DP` cells per cycle
- needs state management across calls
- **sequential**: item `k` costs `k` steps, so it is only selected when items are
  consumed in order. Random access should prefer a fetched codebook.

Lower value than C1 — do it second.

### C3. Retire the current `rematerialize.hpp`  *(~15 min)*

Its `O(index*D)` RNG-replay seek is pathological (819,200 draws to reach row 100 at
D=8192). **Keep the function**, but guard it as the **software reference** for
verification only. Do not let it near synthesis.

---

## D. Plumbing

### D1. Testbench — the critical one  *(~1 hr)*

The paper's central correctness claim is that the manipulator and the flip schedule
produce the same codebook. Assert it:

- **manipulator output is bit-identical to `gen_levels`** for every `(s, n)`
- distance law holds: `d_H(S_s, S_t) == |s-t| * D/(2*(L-1))`
- CA items are mutually near-orthogonal (Hamming ~ D/2)
- per-family draws land in the right value set (catches the A1 bug)

### D2. Characterization  *(~1 hr)*

- generator sweep over `DP` x `Family`
- a `collect_generation.py`
- **add a `materialize` column** to `merge_table.py`'s `COLS` **and to the
  `consistency_check` key** — same fix that `CP` and `port_width` each needed, or
  the points will be flagged as false mismatches

### D3. Estimator  *(~1 hr)*

- `cost_rematerialize` in `DSE/estimator/models/primitives.py` (gates vs cycles)
- `compose.py` must model a codebook read as **either** a gather cost **or** a
  generator cost, selected by `materialize`

---

## Suggested order

| # | Change | Effort | Note |
| --- | --- | --- | --- |
| A1 | `random_hv` tag-dispatch | 30 min | **silent bug — do regardless of the paper** |
| C1 | Level manipulator + TB | 2-3 hr | the headline; refactor from `gen_levels`' permutation |
| B1 | `materialize` interface | 1 hr | makes the variant claim real |
| D1 | Testbench | 1 hr | proves C1 == `gen_levels` |
| C2 | Item automaton | 2 hr | sequential, lower value |
| A2 | `gen_levels` arithmetic path | 2 hr | only if claiming non-binary on-the-fly |
| D2, D3 | Characterization + estimator | 2 hr | **required before any result is published** |

**Minimum viable for the paper's claims to be honest:** A1 + C1 + B1 + D1. That
yields a synthesizable binary level generator, a real `materialize` knob, and proof
it matches `gen_levels`. Items (C2) and the arithmetic path (A2) can follow.

## Definition of done

- [ ] no `std::mt19937` on any synthesizable path
- [ ] manipulator verified bit-identical to `gen_levels` in C-sim
- [ ] `materialize` selectable without changing a consumer's call site
- [ ] generators carry `PIPELINE II=1` + `UNROLL factor=DP` like every other primitive
- [ ] generation rows present in `master_table.csv` / `pareto_table.csv`, 0 mismatches
- [ ] estimator models the fetch-vs-generate choice
- [ ] only then: results may enter the paper's evaluation section
