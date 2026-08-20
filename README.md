# FPGA-HDC-Library (HLS)

A composable primitive library for Hyperdimensional Computing on FPGAs, written
as Vitis HLS function templates. The aim is a set of building blocks in the
spirit of TorchHD, but targeting an FPGA backend, so that an HDC application is
assembled from independently synthesizable primitives rather than written as one
monolithic accelerator.

Two ideas shape the library. The first is that every primitive is
datatype-parametric: the representation is chosen at compile time through a tag
(`binary_tag`, `bipolar_tag`, `fixed_tag`, `integer_tag`, `pow2_tag`) and the
correct operator is selected by tag dispatch, so no multiplexer or unused
operator is synthesized. The second is the separation between application
parameters and architecture parameters. Application parameters, such as the
hypervector dimension, the number of features or classes, and the datatype,
describe what is computed. Architecture parameters, such as dimension
parallelism `DP`, class parallelism `CP`, feature parallelism `FP`, and the
memory tier, describe how it is implemented. A primitive carries no
application-specific constant, so the same template serves any application that
composes it.

The functions are grouped into the same categories used in the paper:
generation, encoding, aggregation and update, search, memory, and control.

## Implemented functions

### Hypervector generation

| Function | Header | Signature |
|---|---|---|
| `random_hv` | `generation/random_hv.hpp` | `template <typename elem_t, int D, int F, typename Family> void random_hv(elem_t codebook[F][D], unsigned seed)` |
| `gen_levels` | `generation/gen_levels.hpp` | `template <typename elem_t, int D, int L, typename Family> void gen_levels(elem_t level[L][D], level_mode_t mode, unsigned seed)` |
| `rematerialize` | `generation/rematerialize.hpp` | `template <typename elem_t, int D> void rematerialize(int index, elem_t out[D], unsigned seed)` |

`random_hv` fills an item codebook with mutually near-orthogonal hypervectors,
drawing each element according to the family tag. `gen_levels` builds a level
codebook whose adjacent levels stay similar while the extremes become nearly
orthogonal. `rematerialize` regenerates a single indexed hypervector from a seed
instead of reading it from a stored codebook, which trades storage for logic.

### Hypervector encoding

| Function | Header | Signature |
|---|---|---|
| `quantize` | `encoding/quantize.hpp` | `template <typename feat_t, typename idx_t, int L> idx_t quantize(feat_t value, feat_t min_val, feat_t max_val)` |
| `bind` | `encoding/bind.hpp` | `template <typename elem_t, int D, typename Family, int DP> void bind(const elem_t a[D], const elem_t b[D], elem_t out[D])` |
| `permute` | `encoding/permute.hpp` | `template <typename elem_t, int D, int DP> void permute(const elem_t in[D], int shift, elem_t out[D])` |
| `scale` | `encoding/scale.hpp` | `template <typename elem_t, typename w_t, int D, int DP, typename Family> void scale(const elem_t in[D], w_t w, elem_t out[D])` |
| `gemm` | `encoding/gemm.hpp` | `template <typename in_t, typename acc_t, int M, int K, int N, int DP, int FP, typename Family> void gemm(const in_t A[M][K], const in_t B[K][N], acc_t C[M][N])` |
| `matvec` | `encoding/matvec.hpp` | `template <typename in_t, typename acc_t, int R, int C, int DP, int FP, typename Family> void matvec(const in_t A[R][C], const in_t x[C], acc_t y[R])` |
| `transpose` | `encoding/transpose.hpp` | `template <typename elem_t, int R, int C, int DP> void transpose(const elem_t in[R][C], elem_t out[C][R])` |
| `flatten` | `encoding/flatten.hpp` | `template <typename elem_t, int R, int C, int DP> void flatten(const elem_t in[R][C], elem_t out[R * C])` |

`bind` is the family-dispatched combining operator: XOR for binary, elementwise
multiply for bipolar, fixed and integer, and an exponent add for power-of-two.
`permute` applies the cyclic rotation used to encode position or sequence order.
`gemm` and `matvec` carry both `DP` and `FP`, so they unroll along two
dimensions.

### Aggregation and update

| Function | Header | Signature |
|---|---|---|
| `bundle` | `aggregation/bundle.hpp` | `template <typename elem_t, typename acc_t, int D, int DP, typename Family> void bundle(const elem_t in[D], acc_t acc[D])` |
| `threshold` | `aggregation/threshold.hpp` | `template <typename acc_t, typename elem_t, int D, typename Family, int DP> void threshold(const acc_t acc[D], elem_t out[D], int count, tie_policy_t tie)` |
| `normalize` | `aggregation/normalize.hpp` | `template <typename elem_t, typename acc_t, int D, int DP, typename Family> void normalize(const elem_t in[D], elem_t out[D])` |
| `update` | `aggregation/update.hpp` | `template <typename proto_t, typename elem_t, int K, int D, int DP, typename Family> void update(proto_t protos[K][D], const elem_t q[D], int label, update_mode_t mode)` |
| `cast` | `aggregation/cast.hpp` | `template <typename in_t, typename out_t, int D, int DP> void cast(const in_t in[D], out_t out[D])` |

`bundle` keeps the accumulator datatype separate from the element datatype, so
the accumulation width is a stage-specific choice rather than a property of the
representation. `threshold` collapses that accumulator back to a prototype:
majority vote for binary, sign for bipolar, passthrough for the arithmetic
families, and a re-encode for power-of-two. Ties are resolved by an exposed tie
policy.

### Precision rules

| Header | Contents |
|---|---|
| `common/hdc_precision.hpp` | `bits_for`, `bundle_acc_bits`, `hamming_score_bits`, `dot_score_bits` |

These are compile-time width rules that derive the accumulator and score widths
from the hypervector dimension and the bundling count, so a design does not have
to fall back on a hand-written constant for each stage.

### Similarity search

| Function | Header | Signature |
|---|---|---|
| `similarity_search` | `search/similarity_search.hpp` | `template <typename elem_t, typename sim_t, int D, int K, typename Family, int DP, int CP> int similarity_search(const elem_t query[D], const elem_t proto[K][D], sim_mode_t mode)` |
| `sim_onchip_hamming`, `sim_onchip_dot` | `search/similarity_search_onchip.hpp` | on-chip prototype array, batched over `QB` queries |
| `sim_buffered_hamming`, `sim_buffered_dot` | `search/similarity_search_buffered.hpp` | off-chip bank read into an on-chip buffer, then scored |
| `similarity_search_stream_dt` | `search/similarity_search_stream_dt.hpp` | prototypes consumed from a stream, datatype-parametric |
| `res_merge` | `search/res_merge.hpp` | merges per-channel winners into a global result |

The search family shares one metric selection. Binary accumulates a Hamming
distance and takes the minimum; the arithmetic families accumulate a dot product
and take the maximum. `DP` unrolls along the dimension and `CP` scores several
prototypes at once. The three variants differ only in where the prototypes live,
which keeps the memory tier separable from the scoring datapath.

### Memory

| Function | Header | Signature |
|---|---|---|
| `gather` | `memory/gather.hpp` | `template <typename elem_t, int N, int D, int DP> void gather(const elem_t codebook[N][D], int index, elem_t out[D])` |
| `place` | `memory/place.hpp` | `template <typename elem_t, int N, int D, int DP> void place(const elem_t in[N][D], elem_t out[N][D])` |
| `hbm_gather` | `memory/hbm_gather.hpp` | `template <int N, int D> void hbm_gather(const hbm_word_t *codebook, int index, hls::stream<hbm_word_t> &out)` |
| `hbm_gather_cp` | `memory/hbm_gather_cp.hpp` | `template <int N, int D> void hbm_gather_cp(...)`, one bank per channel |
| `hbm_gather_cp_scan` | `memory/hbm_gather_cp_scan.hpp` | `template <int N, int D, int NP> void hbm_gather_cp_scan(...)`, contiguous multi-hypervector scan |
| `stream_one`, `sink_one` | `memory/hbm_stream_cp.hpp` | per-channel read engine and consumer for the streaming path |

`gather` reads an indexed hypervector from an on-chip codebook and `hbm_gather`
does the same from off-chip memory, exposing the same contract so the memory
tier can change without touching the connected compute stage. The `_cp` variants
stripe across channels, each with its own port and FIFO. `onchip_tag` and
`offchip_tag` in `common/hdc_types.hpp` mark the tier.

### Control

| Function | Header | Signature |
|---|---|---|
| `initialize_centroids` | `control/initialize_centroids.hpp` | `template <typename elem_t, typename proto_t, int Ns, int K, int D, int DP> void initialize_centroids(const elem_t samples[Ns][D], proto_t centroids[K][D], centroid_init_t mode)` |
| `convergence_check` | `control/convergence_check.hpp` | `template <typename proto_t, int K, int D, int DP, int CP> bool convergence_check(const proto_t nw[K][D], const proto_t old[K][D], long threshold)` |

These support the iterative training and clustering loops. `convergence_check`
counts changed elements per lane and reduces once at the end, so the count does
not become a dependency across the parallel lanes.

### Composition helpers

| Function | Header |
|---|---|
| `encode_feature_value_query`, `encode_ordered_window_query`, `search_binary_references` | `application/shared_composition.hpp` |

Common encoder and search sequences packaged as a single call, expanding to the
same primitives underneath.

## Layout

```
include/
  common/       hdc_types.hpp, hdc_precision.hpp
  generation/   random_hv, gen_levels, rematerialize
  encoding/     quantize, bind, permute, scale, gemm, matvec, transpose, flatten
  aggregation/  bundle, threshold, normalize, update, cast
  search/       similarity_search and its onchip, buffered and streaming variants, res_merge
  memory/       gather, place, hbm_gather, hbm_gather_cp, hbm_gather_cp_scan, hbm_stream_cp
  control/      initialize_centroids, convergence_check
  application/  shared_composition
src/            top-level wrappers, one synthesis entry per category or study
tb/             C-simulation testbenches
scripts/        HLS and synthesis run scripts
```

## Work in progress

The library is still under active development. The primitives above are
implemented and the application-level composition, the design-space exploration
flow, and the on-device evaluation are ongoing.
