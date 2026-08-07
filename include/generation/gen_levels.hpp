/**
 * @file gen_levels.hpp   (Generation)
 * @brief FUNCTION: gen_levels  --  () -> level_codebook : HV[L][D].
 *
 *   Contract:      () -> level_codebook[num_levels][hv_dim]  (persistent)
 *   App (exposed):  hv_dim (D), num_levels (L), codebook datatype, element_bits, level_mode, seed
 *   Arch (deferred): memory_space, banking_factor, materialize
 *
 * Continuous item memory: L HVs where adjacent levels are similar and the
 * extremes are ~orthogonal. LEVEL_LINEAR (baseline) starts from a random level 0
 * and flips D/2 distinct dimensions evenly across the L-1 steps -- ported from
 * the emg_hdc codebook. APPROX_LINEAR / THERMOMETER are level_mode variants to add.
 *
 * STATUS: LEVEL_LINEAR implemented (C-sim pending); other modes = TODO.
 */
#ifndef HDC_GEN_LEVELS_HPP
#define HDC_GEN_LEVELS_HPP

#include <random>
#include <numeric>
#include <algorithm>
#include <vector>
#include "common/hdc_types.hpp"

namespace hdc {

// Map a binary flip-schedule bit to the family's element value. The schedule
// tracks WHICH dimensions differ (binary by nature); the family only decides how
// a 0/1 is represented. Binary keeps {0,1}; bipolar/fixed/integer use {-1,+1};
// pow2 packs the sign with exponent 0 (+/-2^0 = +/-1) rather than casting a bare
// -1 into an unsigned exponent field, which is what the old code did.
template <typename elem_t>
inline elem_t level_elem(int bitval, binary_tag)  { return (elem_t)bitval; }
template <typename elem_t>
inline elem_t level_elem(int bitval, bipolar_tag) { return bitval ? (elem_t)1 : (elem_t)(-1); }
template <typename elem_t>
inline elem_t level_elem(int bitval, fixed_tag)   { return bitval ? (elem_t)1 : (elem_t)(-1); }
template <typename elem_t>
inline elem_t level_elem(int bitval, integer_tag) { return bitval ? (elem_t)1 : (elem_t)(-1); }
template <typename elem_t>
inline elem_t level_elem(int bitval, pow2_tag)    { return (elem_t)pow2_pack(bitval == 0, 0); }

// elem_t = codebook datatype, D = hv_dim, L = num_levels, Family = datatype tag.
// Family defaults to binary_tag, so every existing caller is unchanged.
template <typename elem_t, int D, int L, typename Family = binary_tag>
void gen_levels(elem_t level[L][D], level_mode_t mode = LEVEL_LINEAR, unsigned seed = 43u) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> bit(0, 1);

    // TODO(level_mode): APPROX_LINEAR / THERMOMETER. Baseline handles LINEAR.
    (void)mode;

    std::vector<int> perm(D);
    std::iota(perm.begin(), perm.end(), 0);
    std::shuffle(perm.begin(), perm.end(), rng);   // flip order (each bit flips once)

    std::vector<int> cur(D);
    for (int i = 0; i < D; i++) cur[i] = bit(rng);         // level 0: random bits
    for (int i = 0; i < D; i++) level[0][i] = level_elem<elem_t>(cur[i], Family());

    const int flips_total = D / 2;
    const int per_step     = (L > 1) ? (flips_total / (L - 1)) : 0;

    int p = 0;
    for (int l = 1; l < L; l++) {
        for (int k = 0; k < per_step && p < D; k++, p++)
            cur[perm[p]] ^= 1;                             // flip a fresh distinct bit
        for (int i = 0; i < D; i++) level[l][i] = level_elem<elem_t>(cur[i], Family());
    }
}

} // namespace hdc

#endif // HDC_GEN_LEVELS_HPP
