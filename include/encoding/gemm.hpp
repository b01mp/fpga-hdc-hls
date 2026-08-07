/**
 * @file gemm.hpp   (Encoding)
 * @brief FUNCTION: gemm  --  C[M][N] = A[M][K] * B[K][N]  (dense matmul).
 *
 *   Contract:      (A, B) -> C accumulated in acc_t
 *   App (exposed):  input datatype, accumulator datatype, M / K / N
 *                   (+ template: mesh_compute_mode, kronecker_rank)
 *   Arch (deferred): dimension_parallelism (DP), feature_parallelism (FP)
 *
 * POW2 IS NOT SUPPORTED (see the static_assert). The inner product mixes a
 * multiply (which IS closed under signed powers of two: sign XOR + exponent add)
 * with an ADD across K (which is NOT: 2^a + 2^b is not a power of two). A raw
 * `(acc_t)A * (acc_t)B` on packed exponents is simply wrong. A correct pow2 GEMM
 * would decode each product to a linear value before accumulating -- worth doing
 * if a pow2 projection encoder is ever needed, but it is not on the current path.
 *
 * STATUS: implemented (linear families); C-sim pending.
 */
#ifndef HDC_GEMM_HPP
#define HDC_GEMM_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// in_t = input datatype, acc_t = accumulator datatype. C[M][N] = A[M][K] * B[K][N].
// Family is carried only to reject pow2 at compile time.
template <typename in_t, typename acc_t, int M, int K, int N, int DP = 1, int FP = 1,
          typename Family = binary_tag>
void gemm(const in_t A[M][K], const in_t B[K][N], acc_t C[M][N]) {
    static_assert(!is_pow2_family<Family>::value,
        "gemm() does not support pow2_tag: the multiply is closed under signed "
        "powers of two but the accumulation across K is not. Decode products to "
        "a linear accumulator first if a pow2 projection is required.");
    #pragma HLS ARRAY_PARTITION variable=A type=cyclic factor=FP dim=2
    #pragma HLS ARRAY_PARTITION variable=B type=cyclic factor=FP dim=1
    #pragma HLS ARRAY_PARTITION variable=B type=cyclic factor=DP dim=2
    #pragma HLS ARRAY_PARTITION variable=C type=cyclic factor=DP dim=2
GEMM_ROW:
    for (int m = 0; m < M; m++)
    GEMM_COL:
        for (int n = 0; n < N; n++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL factor=DP
            acc_t sum = 0;
        GEMM_K:
            for (int k = 0; k < K; k++) {
                #pragma HLS UNROLL factor=FP
                sum += (acc_t)A[m][k] * (acc_t)B[k][n];
            }
            C[m][n] = sum;
        }
}

} // namespace hdc

#endif // HDC_GEMM_HPP
