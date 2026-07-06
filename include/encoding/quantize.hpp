/**
 * @file quantize.hpp   (Encoding)
 * @brief FUNCTION: quantize  --  (value, feat_min, feat_max) -> level index.
 *
 *   Contract:      (value : scalar, feat_min, feat_max) -> index in [0, num_levels)
 *   App (exposed):  num_levels  (L),  value/index datatypes
 *   Arch (deferred): feature_parallelism, pipeline_mode
 *
 * Scalar front-end of the continuous item memory: uniform (linear) bucketing of
 * `value` in [feat_min, feat_max] onto one of L level indices. Ported verbatim
 * (behaviour-preserving) from the emg_hdc baseline; datatypes are now template
 * arguments instead of the config typedefs.
 *
 * STATUS: implemented + C-sim tested (tb/tb_encoding.cpp).
 */
#ifndef HDC_QUANTIZE_HPP
#define HDC_QUANTIZE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// feat_t = value datatype (feature_t), idx_t = index datatype (level_idx_t), L = num_levels.
template <typename feat_t, typename idx_t, int L>
idx_t quantize(feat_t value, feat_t min_val, feat_t max_val) {
    if (value <= min_val) return (idx_t)0;
    if (value >= max_val) return (idx_t)(L - 1);

    feat_t span = max_val - min_val;            // > 0 guaranteed by callers
    feat_t norm = (value - min_val) / span;     // in [0,1)
    int    idx  = (int)(norm * (feat_t)L);      // uniform bucket
    if (idx >= L) idx = L - 1;                   // guard fp rounding at the top
    if (idx < 0)  idx = 0;
    return (idx_t)idx;
}

} // namespace hdc

#endif // HDC_QUANTIZE_HPP
