/**
 * @file similarity_search.hpp   (Search)
 * @brief FUNCTION: similarity_search  --  (query, protos[K][D]) -> index.
 *
 *   Contract:      compare query to K prototypes -> best index (or index[top_k]/(index,score))
 *   App (exposed):  num_prototypes (K), similarity datatype, similarity_metric,
 *                   search_mode, early_termination, top_k, hv_dim (D)
 *   Arch (deferred): class_parallelism, dimension_parallelism, memory_space, banking_factor
 *
 * Baseline metric = Hamming distance; SEARCH_ARGMAX on similarity == argmin on
 * Hamming distance. Ported from emg_hdc; element/similarity datatypes are now
 * template arguments and the metric/mode are runtime app-param arguments.
 *
 * NOTE: only SIM_HAMMING + argmax/argmin are wired in the baseline. SIM_COSINE/
 * SIM_DOT, top_k and thresholded modes are later specializations (the metric
 * argument is already threaded through so those branches slot in without a
 * signature change).
 *
 * STATUS: implemented + C-sim tested (tb/tb_search.cpp).
 */
#ifndef HDC_SIMILARITY_SEARCH_HPP
#define HDC_SIMILARITY_SEARCH_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, sim_t = similarity/score datatype, D = hv_dim, K = num_prototypes.
template <typename elem_t, typename sim_t, int D, int K>
int similarity_search(const elem_t query[D], const elem_t proto[K][D],
                      sim_metric_t metric = SIM_HAMMING,
                      search_mode_t mode  = SEARCH_ARGMAX,
                      sim_t *best_score_out = 0) {
    int   best_idx  = 0;
    sim_t best_dist = (sim_t)(D + 1);              // larger than any Hamming distance

SEARCH_CLASSES:
    for (int c = 0; c < K; c++) {
        sim_t dist = 0;
    SEARCH_DIM:
        for (int i = 0; i < D; i++) {
            dist += (sim_t)(query[i] ^ proto[c][i]);   // Hamming = mismatch count
        }
        if (dist < best_dist) {                    // argmin distance == argmax similarity
            best_dist = dist;
            best_idx  = c;
        }
    }
    if (best_score_out) *best_score_out = best_dist;
    return best_idx;
}

} // namespace hdc

#endif // HDC_SIMILARITY_SEARCH_HPP
