/**
 * @file gather.hpp   (Memory)
 * @brief FUNCTION: gather  --  (codebook, index) -> HV  (indexed lookup).
 *
 *   Contract:      (codebook[N][D], index) -> HV[D]
 *   App (exposed):  num_features / num_levels (N = address space), hv_dim (D)
 *   Arch (deferred): memory_space, banking_factor
 *
 * Reads one hypervector row out of a codebook / item memory by index. This is the
 * memory-read that rematerialize() replaces with regeneration.
 *
 * STATUS: implemented; C-sim pending.
 */
#ifndef HDC_GATHER_HPP
#define HDC_GATHER_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, N = codebook rows (address space), D = hv_dim,
// DP = dimension_parallelism (elements read per step; default 1 = sequential).
template <typename elem_t, int N, int D, int DP = 1>
void gather(const elem_t codebook[N][D], int index, elem_t out[D]) {
    #pragma HLS ARRAY_PARTITION variable=codebook type=cyclic factor=DP dim=2
    #pragma HLS ARRAY_PARTITION variable=out      type=cyclic factor=DP dim=1
GATHER_LOOP:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        out[i] = codebook[index][i];
    }
}

} // namespace hdc

#endif // HDC_GATHER_HPP
