/**
 * @file matvec.hpp   (Encoding)
 * @brief FUNCTION: matvec  --  y[R] = A[R][C] * x[C]  (matrix-vector product).
 *
 *   Contract:      (A, x) -> y accumulated in acc_t
 *   App (exposed):  input datatype, accumulator datatype, R / C
 *   Arch (deferred): dimension_parallelism (DP), feature_parallelism (FP)
 *
 * POW2 IS NOT SUPPORTED (see the static_assert) -- same reason as gemm(): the
 * per-element multiply is closed under signed powers of two, but the sum across
 * C is not, and a raw multiply on packed exponents is wrong.
 *
 * STATUS: implemented (linear families); C-sim pending.
 */
#ifndef HDC_MATVEC_HPP
#define HDC_MATVEC_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// in_t = input datatype, acc_t = accumulator datatype. y[R] = A[R][C] * x[C].
// Family is carried only to reject pow2 at compile time.
template <typename in_t, typename acc_t, int R, int C, int DP = 1, int FP = 1,
          typename Family = binary_tag>
void matvec(const in_t A[R][C], const in_t x[C], acc_t y[R]) {
    static_assert(!is_pow2_family<Family>::value,
        "matvec() does not support pow2_tag: the multiply is closed under signed "
        "powers of two but the accumulation across C is not. Decode products to "
        "a linear accumulator first if a pow2 projection is required.");
    #pragma HLS ARRAY_PARTITION variable=A type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=A type=cyclic factor=FP dim=2
    #pragma HLS ARRAY_PARTITION variable=x type=cyclic factor=FP dim=1
    #pragma HLS ARRAY_PARTITION variable=y type=cyclic factor=DP dim=1
MATVEC_ROW:
    for (int r = 0; r < R; r++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=DP
        acc_t sum = 0;
    MATVEC_COL:
        for (int c = 0; c < C; c++) {
            #pragma HLS UNROLL factor=FP
            sum += (acc_t)A[r][c] * (acc_t)x[c];
        }
        y[r] = sum;
    }
}

} // namespace hdc

#endif // HDC_MATVEC_HPP
