/**
 * @file cast.hpp   (Aggregation & Update)
 * @brief FUNCTION: cast  --  (in : HV) -> HV  (datatype conversion).
 *
 *   Contract:      (in) -> out, datatype-converted (reinterpret / widen / narrow)
 *   App (exposed):  target datatype, element_bits, hv_dim (D)
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * Element-wise datatype conversion between library stages (codebook -> input ->
 * prototype -> similarity). Baseline uses a value-preserving static conversion;
 * reinterpret vs widen vs narrow is a conversion-kind select added later.
 *
 * STATUS: implemented (value conversion); C-sim pending.
 */
#ifndef HDC_CAST_HPP
#define HDC_CAST_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// in_t = source datatype, out_t = target datatype, D = hv_dim.
template <typename in_t, typename out_t, int D>
void cast(const in_t in[D], out_t out[D]) {
CAST_LOOP:
    for (int i = 0; i < D; i++)
        out[i] = (out_t)in[i];
}

} // namespace hdc

#endif // HDC_CAST_HPP
