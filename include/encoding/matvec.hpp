/**
 * @file matvec.hpp   (Encoding)
 * @brief FUNCTION: matvec  --  (A : HM, x : HV) -> HV  (single-sample projection).
 *
 *   Contract:      (A[R][C], x[C]) -> y[R]
 *   App (exposed):  hv_dim, num_features, input datatype, accumulator_bits
 *   Arch (deferred): feature/dimension_parallelism, memory_space, pipeline_mode
 *
 * One-sample projection (a row of gemm). MAC each matrix row against the input
 * vector into a wide accumulator.
 *
 * STATUS: implemented (reference); C-sim pending.
 */
#ifndef HDC_MATVEC_HPP
#define HDC_MATVEC_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// in_t = input datatype, acc_t = accumulator datatype. y[R] = A[R][C] * x[C].
template <typename in_t, typename acc_t, int R, int C>
void matvec(const in_t A[R][C], const in_t x[C], acc_t y[R]) {
MATVEC_ROW:
    for (int r = 0; r < R; r++) {
        acc_t sum = 0;
    MATVEC_COL:
        for (int c = 0; c < C; c++)
            sum += (acc_t)A[r][c] * (acc_t)x[c];
        y[r] = sum;
    }
}

} // namespace hdc

#endif // HDC_MATVEC_HPP
