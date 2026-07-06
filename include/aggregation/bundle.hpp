/**
 * @file bundle.hpp   (Aggregation & Update)
 * @brief FUNCTION: bundle (accumulate)  --  (in : HV, acc : ACC[D]) -> ACC[D].
 *
 *   Contract:      superpose `in` into running accumulator `acc`
 *   App (exposed):  input datatype, accumulator datatype/bits (accumulator_bits), hv_dim (D)
 *   Arch (deferred): dimension_parallelism, feature_parallelism, pipeline_mode
 *
 * Bundling is the "add" of majority voting; the majority itself is applied later
 * by threshold(). Keeping accumulate and threshold separate lets one accumulator
 * serve both the per-sample encode (count = num_features) and the per-class
 * prototype build (count = #samples in class). Ported from emg_hdc; element and
 * accumulator datatypes are now template arguments.
 *
 * NOTE(bipolar): map {0->-1, 1->+1} before accumulate for a bipolar element.
 *
 * STATUS: implemented + C-sim tested (tb/tb_aggregation.cpp).
 */
#ifndef HDC_BUNDLE_HPP
#define HDC_BUNDLE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = input element datatype, acc_t = accumulator datatype, D = hv_dim.
template <typename elem_t, typename acc_t, int D>
void bundle(const elem_t in[D], acc_t acc[D]) {
BUNDLE_LOOP:
    for (int i = 0; i < D; i++) {
        acc[i] += (acc_t)in[i];
    }
}

} // namespace hdc

#endif // HDC_BUNDLE_HPP
