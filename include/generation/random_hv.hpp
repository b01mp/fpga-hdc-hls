/**
 * @file random_hv.hpp   (Generation)
 * @brief FUNCTION: random_hv  --  () -> codebook : HV[F][D].
 *
 *   Contract:      () -> codebook[num_features][hv_dim]  (persistent)
 *   App (exposed):  hv_dim (D), num_features (F), codebook datatype, element_bits, seed
 *   Arch (deferred): memory_space, banking_factor, materialize, dimension_parallelism
 *
 * F random, ~orthogonal binary base hypervectors (record encoding item memory).
 * Host-side, deterministic (std::mt19937 from `seed`) so a SW reference and the
 * hardware share identical codebooks -- same policy as the emg_hdc baseline.
 * Drawn row-major: row f occupies draws [f*D, (f+1)*D), which rematerialize()
 * relies on to regenerate a single row without storing the codebook.
 *
 * STATUS: implemented (baseline binary); C-sim pending.
 */
#ifndef HDC_RANDOM_HV_HPP
#define HDC_RANDOM_HV_HPP

#include <random>
#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = codebook datatype, D = hv_dim, F = num_features.
template <typename elem_t, int D, int F>
void random_hv(elem_t codebook[F][D], unsigned seed = 42u) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> bit(0, 1);
    for (int f = 0; f < F; f++)
        for (int i = 0; i < D; i++)
            codebook[f][i] = (elem_t)bit(rng);
}

} // namespace hdc

#endif // HDC_RANDOM_HV_HPP
