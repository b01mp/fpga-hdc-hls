/**
 * @file bind.hpp   (Encoding)
 * @brief FUNCTION: bind  --  (a : HV, b : HV) -> HV  (element-wise associate).
 *
 *   Contract:      (a, b) -> out, out datatype inherited from inputs
 *   App (exposed):  element datatype, hv_dim (D)   (output-datatype override -> cast)
 *   Arch (deferred): dimension_parallelism, pipeline_mode, memory_space
 *
 * Binary baseline => XOR (self-inverse, distributes over bundling). Produces a
 * vector dissimilar to both inputs. Ported from emg_hdc; element type is now a
 * template argument.
 *
 * NOTE(bipolar/fixed): for a non-binary element datatype the bind op becomes
 * a[i]*b[i] instead of XOR. That op-select-by-datatype is a later specialization;
 * the binary baseline keeps XOR.
 *
 * STATUS: implemented + C-sim tested (tb/tb_encoding.cpp).
 */
#ifndef HDC_BIND_HPP
#define HDC_BIND_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype (binary baseline), D = hv_dim.
template <typename elem_t, int D>
void bind(const elem_t a[D], const elem_t b[D], elem_t out[D]) {
BIND_LOOP:
    for (int i = 0; i < D; i++) {
        out[i] = (elem_t)(a[i] ^ b[i]);   // binary XOR bind
    }
}

} // namespace hdc

#endif // HDC_BIND_HPP
