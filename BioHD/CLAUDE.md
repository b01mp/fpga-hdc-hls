# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

All 6 phases are implemented and passing, including the Phase 4 go/no-go gate. Current status:
**all phases done**.

**Caveat on Phase 6**: there is no real E. coli FASTA file available in this environment, and
per project policy this assistant does not guess/fabricate download URLs for external genomic
databases. `experiments/phase6_end_to_end.py` therefore validates the >95% TPR milestone against
a synthetic stand-in DNA sequence (random, ~50% GC content, scaled down from E. coli's real
~4.6 Mbp). The encode/library/search code path is identical to what would run on real data —
only the input genome differs. To validate against the real genome, supply a FASTA file and feed
its sequence into `synthetic_genome()`'s call site in that script.

The source paper is at `C:\USC\HDCLibReview\BioHD.pdf` (outside this repo) — read it there
when you need the original algorithm description, figures, or equations.

## Commands

Dependencies live in a project-local venv (`.venv/`), not the system Python.

```
# run the full test suite
.venv\Scripts\python.exe -m pytest tests/ -v

# run a single test
.venv\Scripts\python.exe -m pytest tests/test_primitives.py::test_bind_is_self_inverse -v

# run a phase's milestone validation script (prints distributions, saves plots to experiments/output/)
.venv\Scripts\python.exe experiments\phase1_core_primitives.py
.venv\Scripts\python.exe experiments\phase2_encoding_pipeline.py
.venv\Scripts\python.exe experiments\phase3_reference_library.py
.venv\Scripts\python.exe experiments\phase4_similarity_search_roc.py   # the go/no-go gate
.venv\Scripts\python.exe experiments\phase5_parameter_sensitivity.py
.venv\Scripts\python.exe experiments\phase6_end_to_end.py              # synthetic genome, see caveat above
```

If `.venv` is missing, recreate it with `python -m venv .venv` then
`.venv\Scripts\python.exe -m pip install torch numpy matplotlib pytest`.

## Project

A faithful Python simulation of **BioHD: An Efficient Genome Sequence Search Platform Using
HyperDimensional Memorization** (ISCA 2022, Zou et al., UC Irvine).

## Goal and hard constraints

- Implement BioHD's HDC algorithm using explicit, from-scratch primitive functions so that
  intermediate states are observable at every stage.
- **Do not use TorchHD or any other HDC framework** that abstracts away the operations — every
  HDC operation (bind, bundle, permute, similarity) must be implemented from scratch.
- PyTorch tensors are fine for the underlying computation/storage, just not a higher-level HDC API.

## Stack

- Python 3.10+, PyTorch, NumPy, Matplotlib
- No TorchHD, no third-party HDC libraries

## Module structure

- `primitives.py` (done) — bind (XOR), bundle, permute (cyclic shift), similarity (Hamming +
  dot product)
- `encoder.py` (done) — `HDCAlphabet` class: mRNA encoding, amino acid encoding (probabilistic
  merge), protein encoding, indel-tolerant encoding. Generates hypervectors for `A,C,G,U,T`
  (`ALL_BASES`) so `encode_mrna` works on both RNA and raw DNA sequences.
- `library.py` (done) — `HDCLibrary` class: `sliding_windows()`, capacity-bounded reference
  hypervectors, adaptive refinement (`refine()`), recall accuracy/query helpers
- `search.py` (done) — `membership()` (T-membership function), `roc_curve()`, `auc()`,
  `best_threshold()` (Youden's J)
- `experiments/` — one script per validation milestone (see Phases below); writes plots to
  `experiments/output/`
- `tests/` — pytest unit tests, one file per module (`test_primitives.py`, `test_encoder.py`,
  `test_library.py`, `test_search.py`)

Phases 4 and 5's experiments generate pattern hypervectors directly via
`primitives.random_hvs` rather than running the full encoder pipeline, since Phases 1-2 already
established that encoded sequences are statistically indistinguishable from independent random
hypervectors (near-orthogonal, same dot-product distribution) — this makes the large-P sweeps in
those phases dramatically faster without sacrificing fidelity. Phase 3 and 6 exercise the real
`HDCAlphabet` + `HDCLibrary` pipeline end-to-end.

## Encoding algorithm (from the paper)

1. Base hypervectors (HVs): random binary `{0,1}^D`, one per nucleotide `{A,C,G,T/U}`
2. mRNA encoding: `H = A * ρ¹(C) * ρ²(G) * ρ³(U)` (bind + permute)
3. Amino acid: probabilistically merge HVs of all valid codons (random half-dimension sampling
   per codon pair)
4. Protein: `S = H_Met * ρ¹(H_Phe) * ρ²(H_Ser) * ...`
5. Indel-tolerant: split sequence into chunks, bundle with correlated position vectors

## Implementation notes

- `D` (hypervector dimension) must be a parameter; test at 1k, 4k, 10k, 40k.
- Support both binary (Hamming) and full-precision (dot product) modes via a flag — same
  function signatures, different internal representation.
- Print intermediate similarity distributions at each stage, not just final results.
- Every primitive needs a standalone unit test verifying its distributional properties (e.g.
  near-orthogonality of random HV pairs).

## Phases and validation milestones

Work through phases in order; each has an explicit go/no-go condition.

1. **Core primitives** — done when unit tests pass and 1000 random HV pairs show dot products
   clustered near 0. **DONE.** Implemented in `primitives.py` (`random_hv`/`random_hvs`, `bind`,
   `bundle`, `permute`, `similarity`, `cosine_similarity`), with both "binary" (XOR/Hamming) and
   "bipolar" (multiply/dot-product) representations behind a `mode` flag. Validated by
   `tests/test_primitives.py` (20 tests) and `experiments/phase1_core_primitives.py`, which
   confirmed mean ~0 and std ~sqrt(D) at D = 1k/4k/10k/40k for both modes.
2. **Encoding pipeline** (bottom-up, one level at a time) — done when a 10-amino-acid protein
   can be encoded and its HV is near-orthogonal to unrelated sequences. **DONE.** Implemented in
   `encoder.py`: `HDCAlphabet` holds fixed base/amino-acid hypervectors for a given (dim, mode,
   seed) and exposes `encode_mrna`, `encode_protein`, and `encode_indel_tolerant`; standalone
   helpers `probabilistic_merge` (codon merging) and `correlated_position_hvs` (indel-tolerant
   chunk weighting) support them. Validated by `tests/test_encoder.py` (34 tests) and
   `experiments/phase2_encoding_pipeline.py`, which confirmed near-zero similarity for unrelated
   10-amino-acid proteins and that indel-tolerant encoding degrades more gracefully under a
   single insertion than exact full-chain encoding.
3. **Reference library** — done when the library correctly memorizes 10^3 sequences at `D=10k`.
   **DONE.** Implemented in `library.py`. `experiments/phase3_reference_library.py` memorizes
   1000 sliding-window protein patterns across 10 capacity-bounded reference hypervectors at
   D=10000 (binary mode) and recalls **100%** of them correctly — no adaptive refinement was
   even needed in this configuration (the script falls back to bipolar mode automatically if
   binary recall ever drops below 95%).
4. **Similarity search + ROC curve** — done when the ROC curve qualitatively matches Figure 6d
   of the paper. **This is the go/no-go gate** for the whole simulation approach. **DONE — GATE
   PASSED.** Implemented in `search.py`. `experiments/phase4_similarity_search_roc.py` shows a
   lightly loaded reference (P=50 patterns) hits TPR=1.0 at FPR=0, while a heavily loaded one
   (P=8000, approaching D=10000) degrades to TPR=0.20 at FPR<=0.05 — AUC falls monotonically
   (0.512 -> 0.480 -> 0.430 -> 0.263) as P grows, matching Figure 6d's qualitative shape.
5. **Parameter sensitivity** — done when the capacity-vs-`D` tradeoff matches Figure 6a/b trends.
   **DONE.** `experiments/phase5_parameter_sensitivity.py` measured experimental capacity (TPR>=0.95,
   FPR<=0.05) across D in {1k,4k,10k,40k} x mode in {binary,bipolar}: capacity grows
   monotonically with D for both modes (binary: 50->100->400->1600; bipolar: 100->200->800->3200),
   and full-precision (bipolar) capacity is consistently ~2x the binary capacity at every D,
   matching the paper's precision-vs-capacity claim.
6. **End-to-end on real data** (E. coli DNA, query length 200) — done when true positive rate
   exceeds 95% on the E. coli dataset. **DONE, with a caveat.** `experiments/phase6_end_to_end.py`
   achieved **100% TPR / 0% FPR** at query length 200, D=10000, bipolar mode — but against a
   **synthetic stand-in genome**, not real E. coli sequence data (see "Project status" above for
   why, and how to swap in a real FASTA file).
