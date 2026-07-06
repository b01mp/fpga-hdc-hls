/**
 * @file normalize.hpp   (Aggregation & Update)
 * @brief FUNCTION: normalize  --  (in : HV) -> HV  (L2 / scale normalized).
 *
 *   Contract:      (in) -> out, L2 / scale normalized
 *   App (exposed):  input datatype, accumulator datatype, hv_dim (D)
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * L2 normalization. Meaningful for real/fixed-point elements (cosine pipelines);
 * for a 1-bit binary element normalize is a no-op-ish identity. The norm is
 * computed in a wide/real accumulator, then each element is rescaled.
 *
 * STATUS: skeleton -- baseline L2 body written; REVIEW output-datatype semantics
 * (integer elem_t loses precision on divide) before using in an app.
 */
#ifndef HDC_NORMALIZE_HPP
#define HDC_NORMALIZE_HPP

#include <cmath>
#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, acc_t = accumulator datatype for the norm, D = hv_dim.
template <typename elem_t, typename acc_t, int D>
void normalize(const elem_t in[D], elem_t out[D]) {
    acc_t sumsq = 0;
NORM_ACC:
    for (int i = 0; i < D; i++) sumsq += (acc_t)in[i] * (acc_t)in[i];

    double norm = std::sqrt((double)sumsq);
    if (norm == 0.0) norm = 1.0;                   // avoid div-by-zero on all-zero HV
NORM_SCALE:
    for (int i = 0; i < D; i++)
        out[i] = (elem_t)((double)in[i] / norm);   // REVIEW: precision for integer elem_t
}

} // namespace hdc

#endif // HDC_NORMALIZE_HPP
