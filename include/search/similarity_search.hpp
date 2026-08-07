/**
 * @file similarity_search.hpp   (Search)
 * @brief FUNCTION: similarity_search  --  (query, protos[K][D]) -> index.
 *
 *   Contract:      compare query to K prototypes -> best index (or index[top_k]/(index,score))
 *   App (exposed):  num_prototypes (K), similarity datatype, similarity_metric,
 *                   search_mode, early_termination, top_k, hv_dim (D)
 *   Arch (deferred): class_parallelism, dimension_parallelism, memory_space, banking_factor
 *
 * Datatype-parametric (Novelty 1): the metric datapath AND the search direction
 * are selected at COMPILE time by a family tag -- Hamming distance + argmin
 * (binary), dot-product similarity + argmax (bipolar/fixed/integer/pow2). The
 * runtime metric/mode args are kept for signature compatibility but the family
 * drives the behavior.
 *
 * NOTE: top_k / thresholded / early_termination modes are still deferred.
 *
 * STATUS: datatype-parametric (binary=Hamming, others=dot) + C-sim tested.
 */
#ifndef HDC_SIMILARITY_SEARCH_HPP
#define HDC_SIMILARITY_SEARCH_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// --- Per-family per-element score contribution (accumulated into sim_t) ---
//   binary : XOR  -> accumulates a Hamming DISTANCE     (lower  = more similar)
//   others : a*b  -> accumulates a dot-product SIMILARITY (higher = more similar)
//   pow2   : the product of two signed powers of two is itself a signed power of
//            two (sign XOR, exponent ADD), which is then DECODED to a linear
//            value so it can be summed. Multiply-free: an adder plus a shift,
//            never a DSP. Summing the exponents directly would be wrong --
//            2^a + 2^b is not a power of two.
template <typename S, typename T> inline S sim_elem(T a, T b, binary_tag)  { return (S)(a ^ b); }
template <typename S, typename T> inline S sim_elem(T a, T b, bipolar_tag) { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, fixed_tag)   { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, integer_tag) { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, pow2_tag) {
    // NOTE: deliberately NOT routed through pow2_bind(), which saturates the
    // exponent to fit a pow2_t. The product is only ever consumed as a linear
    // value here, so the exponent sum is taken at full width. The caller must
    // size S for (max product exponent + log2(D)) headroom.
    pow2_t pa = (pow2_t)a, pb = (pow2_t)b;
    int k = (int)pow2_exp(pa) + (int)pow2_exp(pb);
    S mag = (S)(((S)1) << k);
    return (pow2_sign(pa) ^ pow2_sign(pb)) ? (S)(-mag) : mag;
}

// --- Per-family search direction: is a LARGER accumulated score "more similar"? ---
inline bool sim_higher_better(binary_tag)  { return false; }  // Hamming distance: minimize
inline bool sim_higher_better(bipolar_tag) { return true;  }  // dot product:     maximize
inline bool sim_higher_better(fixed_tag)   { return true;  }
inline bool sim_higher_better(integer_tag) { return true;  }
inline bool sim_higher_better(pow2_tag)    { return true;  }

// elem_t = element datatype, sim_t = score datatype, D = hv_dim, K = num_prototypes,
// Family = datatype-family tag, DP = dimension_parallelism, CP = class_parallelism.
template <typename elem_t, typename sim_t, int D, int K,
          typename Family = binary_tag, int DP = 1, int CP = 1>
int similarity_search(const elem_t query[D], const elem_t proto[K][D],
                      sim_metric_t metric = SIM_HAMMING,
                      search_mode_t mode  = SEARCH_ARGMAX,
                      sim_t *best_score_out = 0) {
    #pragma HLS ARRAY_PARTITION variable=query type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=proto type=cyclic factor=CP dim=1
    #pragma HLS ARRAY_PARTITION variable=proto type=cyclic factor=DP dim=2
    (void)metric; (void)mode;                      // family selects metric + direction
    const bool higher_better = sim_higher_better(Family());

    // Seed with class 0, then compare the rest (avoids +/-inf init across metrics).
    sim_t best_score = 0;
SEED_DIM:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        best_score += sim_elem<sim_t>(query[i], proto[0][i], Family());
    }
    int best_idx = 0;

SEARCH_CLASSES:
    for (int c = 1; c < K; c++) {
        #pragma HLS UNROLL factor=CP
        sim_t score = 0;
    SEARCH_DIM:
        for (int i = 0; i < D; i++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL   factor=DP
            score += sim_elem<sim_t>(query[i], proto[c][i], Family());
        }
        bool better = higher_better ? (score > best_score) : (score < best_score);
        if (better) { best_score = score; best_idx = c; }
    }
    if (best_score_out) *best_score_out = best_score;
    return best_idx;
}

} // namespace hdc

#endif // HDC_SIMILARITY_SEARCH_HPP
