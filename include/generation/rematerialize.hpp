/**
 * @file rematerialize.hpp   (Generation)
 * @brief FUNCTION: rematerialize  --  (index) -> HV[D]  (on-demand single HV).
 *
 *   Contract:      (index) -> HV[hv_dim]   (regenerate instead of storing)
 *   App (exposed):  hv_dim (D), codebook datatype, element_bits, seed, level_mode
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * Regenerates one hypervector on demand rather than reading it from a stored
 * codebook (memory-vs-logic trade). This baseline reproduces one *row* of
 * random_hv(): same seed, same row-major draw order, so rematerialize<...>(f)
 * equals random_hv(...)[f]. That keeps a rematerialized encoder bit-identical to
 * the stored-codebook path it replaces.
 *
 * STATUS: implemented (matches random_hv row); C-sim pending.
 * TODO(level_mode): a gen_levels-equivalent regeneration (correlated levels)
 * needs the flip schedule replayed, not just a per-row skip.
 */
#ifndef HDC_REMATERIALIZE_HPP
#define HDC_REMATERIALIZE_HPP

#include <random>
#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = codebook datatype, D = hv_dim. `index` selects which HV row to regenerate.
template <typename elem_t, int D>
void rematerialize(int index, elem_t out[D], unsigned seed = 42u) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> bit(0, 1);
    for (int skip = 0; skip < index * D; skip++) bit(rng);   // advance to row `index`
    for (int i = 0; i < D; i++) out[i] = (elem_t)bit(rng);
}

} // namespace hdc

#endif // HDC_REMATERIALIZE_HPP
