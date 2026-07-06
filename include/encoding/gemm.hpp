/**
 * @file gemm.hpp   (Encoding)
 * @brief FUNCTION: gemm  --  (A : HM, B : HM) -> HM  (dense matrix multiply).
 *
 *   Contract:      (A[M][K], B[K][N]) -> C[M][N]   (projection / RFF encoder)
 *   App (exposed):  hv_dim, num_features, input datatype, accumulator_bits
 *                   (+ template: mesh_compute_mode, kronecker_rank)
 *   Arch (deferred): feature/dimension_parallelism, memory_space, banking_factor, pipeline_mode
 *
 * Textbook triple-loop MAC into a wide accumulator; the projection/RFF front-end
 * for MeshHD-style encoders. Tiling / MAC-array structure are architecture knobs
 * added later -- this is the correctness reference.
 *
 * STATUS: implemented (reference triple-loop); C-sim pending.
 */
#ifndef HDC_GEMM_HPP
#define HDC_GEMM_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// in_t = input datatype, acc_t = accumulator datatype. C[M][N] = A[M][K] * B[K][N].
template <typename in_t, typename acc_t, int M, int K, int N>
void gemm(const in_t A[M][K], const in_t B[K][N], acc_t C[M][N]) {
GEMM_ROW:
    for (int m = 0; m < M; m++)
    GEMM_COL:
        for (int n = 0; n < N; n++) {
            acc_t sum = 0;
        GEMM_K:
            for (int k = 0; k < K; k++)
                sum += (acc_t)A[m][k] * (acc_t)B[k][n];
            C[m][n] = sum;
        }
}

} // namespace hdc

#endif // HDC_GEMM_HPP
