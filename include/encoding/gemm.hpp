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
template <typename in_t, typename acc_t, int M, int K, int N, int DP = 1, int FP = 1>
void gemm(const in_t A[M][K], const in_t B[K][N], acc_t C[M][N]) {
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
