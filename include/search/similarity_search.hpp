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
template <typename S, typename T> inline S sim_elem(T a, T b, binary_tag)  { return (S)(a ^ b); }
template <typename S, typename T> inline S sim_elem(T a, T b, bipolar_tag) { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, fixed_tag)   { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, integer_tag) { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, pow2_tag)    { return (S)(a * b); }

// --- Per-family search direction: is a LARGER accumulated score "more similar"? ---
inline bool sim_higher_better(binary_tag)  { return false; }  // Hamming distance: minimize
inline bool sim_higher_better(bipolar_tag) { return true;  }  // dot product:     maximize
inline bool sim_higher_better(fixed_tag)   { return true;  }
inline bool sim_higher_better(integer_tag) { return true;  }
inline bool sim_higher_better(pow2_tag)    { return true;  }

// elem_t = element datatype, sim_t = score datatype, D = hv_dim, K = num_prototypes,
// Family = datatype-family tag (default binary_tag => Hamming/argmin; callers unchanged).
template <typename elem_t, typename sim_t, int D, int K, typename Family = binary_tag>
int similarity_search(const elem_t query[D], const elem_t proto[K][D],
                      sim_metric_t metric = SIM_HAMMING,
                      search_mode_t mode  = SEARCH_ARGMAX,
                      sim_t *best_score_out = 0) {
    (void)metric; (void)mode;                      // family selects metric + direction
    const bool higher_better = sim_higher_better(Family());

    // Seed with class 0, then compare the rest (avoids +/-inf init across metrics).
    sim_t best_score = 0;
SEED_DIM:
    for (int i = 0; i < D; i++)
        best_score += sim_elem<sim_t>(query[i], proto[0][i], Family());
    int best_idx = 0;

SEARCH_CLASSES:
    for (int c = 1; c < K; c++) {
        sim_t score = 0;
    SEARCH_DIM:
        for (int i = 0; i < D; i++)
            score += sim_elem<sim_t>(query[i], proto[c][i], Family());
        bool better = higher_better ? (score > best_score) : (score < best_score);
        if (better) { best_score = score; best_idx = c; }
    }
    if (best_score_out) *best_score_out = best_score;
    return best_idx;
}

} // namespace hdc

#endif // HDC_SIMILARITY_SEARCH_HPP
