/**
 * @file random_hv.hpp   (Generation)
 * @brief FUNCTION: random_hv  --  () -> codebook : HV[F][D].
 *
 *   Contract:      () -> codebook[num_features][hv_dim]  (persistent)
 *   App (exposed):  hv_dim (D), num_features (F), codebook datatype, element_bits, seed
 *   Arch (deferred): memory_space, banking_factor, materialize, dimension_parallelism
 *
 * F random, ~orthogonal base hypervectors (record encoding item memory).
 * Host-side, deterministic (std::mt19937 from `seed`) so a SW reference and the
 * hardware share identical codebooks -- same policy as the emg_hdc baseline.
 * Drawn row-major: row f occupies draws [f*D, (f+1)*D), which rematerialize()
 * relies on to regenerate a single row without storing the codebook.
 *
 * STATUS: implemented (binary/bipolar/fixed/integer/pow2); C-sim pending.
 */
#ifndef HDC_RANDOM_HV_HPP
#define HDC_RANDOM_HV_HPP

#include <random>
#include "common/hdc_types.hpp"

namespace hdc {

// Per-family element draw -- selects, at COMPILE time (tag dispatch), the value
// SET the codebook is drawn from. This is the generation-side of the datatype-
// parametric story: previously every family drew bit(0,1) and cast, so a bipolar
// codebook was silently {0,1} instead of {-1,+1}. Now each family draws its own
// representation.
template <typename elem_t>
inline elem_t draw_elem(std::mt19937 &rng, binary_tag) {
    std::uniform_int_distribution<int> b(0, 1);
    return (elem_t)b(rng);                                 // {0, 1}
}
template <typename elem_t>
inline elem_t draw_elem(std::mt19937 &rng, bipolar_tag) {
    std::uniform_int_distribution<int> b(0, 1);
    return b(rng) ? (elem_t)1 : (elem_t)(-1);              // {-1, +1}
}
template <typename elem_t>
inline elem_t draw_elem(std::mt19937 &rng, fixed_tag) {
    std::uniform_int_distribution<int> b(0, 1);
    return b(rng) ? (elem_t)1 : (elem_t)(-1);              // +/-1 base HV, fixed-point
}
template <typename elem_t>
inline elem_t draw_elem(std::mt19937 &rng, integer_tag) {
    std::uniform_int_distribution<int> b(0, 1);
    return b(rng) ? (elem_t)1 : (elem_t)(-1);              // +/-1 base HV, integer
}
// pow2: a base hypervector element is +/-1 == +/-2^0, so the exponent is 0 and
// only the SIGN is random. Drawing +/-1 directly into the packed type would
// corrupt it (the old code did exactly that, writing -1 into an unsigned field).
template <typename elem_t>
inline elem_t draw_elem(std::mt19937 &rng, pow2_tag) {
    std::uniform_int_distribution<int> b(0, 1);
    return (elem_t)pow2_pack(b(rng) == 0, 0);              // {-2^0, +2^0}
}

// elem_t = codebook datatype, D = hv_dim, F = num_features, Family = datatype tag.
// Family defaults to binary_tag, so every existing caller is unchanged.
template <typename elem_t, int D, int F, typename Family = binary_tag>
void random_hv(elem_t codebook[F][D], unsigned seed = 42u) {
    std::mt19937 rng(seed);
    for (int f = 0; f < F; f++)
        for (int i = 0; i < D; i++)
            codebook[f][i] = draw_elem<elem_t>(rng, Family());
}

} // namespace hdc

#endif // HDC_RANDOM_HV_HPP
