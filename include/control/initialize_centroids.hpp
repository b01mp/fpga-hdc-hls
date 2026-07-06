/**
 * @file initialize_centroids.hpp   (Control)
 * @brief FUNCTION: initialize_centroids  --  (samples) -> STORE  (seed clusters).
 *
 *   Contract:      (samples[Ns][D]) -> centroids[K][D]   (seed cluster centers)
 *   App (exposed):  num_prototypes (K), prototype datatype, seed
 *                   (+ template: centroid_init_mode)
 *   Arch (deferred): memory_space, banking_factor
 *
 * Seeds K cluster centers for a clustering / online-HDC pass. CINIT_SAMPLE picks
 * K distinct sample rows (evenly strided); CINIT_RANDOM draws random binary
 * centers. Host-side deterministic via `seed`.
 *
 * STATUS: skeleton -- both modes have a baseline body; C-sim pending.
 */
#ifndef HDC_INITIALIZE_CENTROIDS_HPP
#define HDC_INITIALIZE_CENTROIDS_HPP

#include <random>
#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = sample datatype, proto_t = centroid datatype.
// Ns = num_samples, K = num_prototypes, D = hv_dim.
template <typename elem_t, typename proto_t, int Ns, int K, int D>
void initialize_centroids(const elem_t samples[Ns][D], proto_t centroids[K][D],
                          centroid_init_t mode = CINIT_SAMPLE, unsigned seed = 42u) {
    if (mode == CINIT_RANDOM) {
        std::mt19937 rng(seed);
        std::uniform_int_distribution<int> bit(0, 1);
        for (int k = 0; k < K; k++)
            for (int i = 0; i < D; i++)
                centroids[k][i] = (proto_t)bit(rng);
    } else { // CINIT_SAMPLE: evenly-strided sample rows
        const int stride = (K > 0 && Ns > K) ? (Ns / K) : 1;
        for (int k = 0; k < K; k++) {
            int row = (k * stride) % Ns;
            for (int i = 0; i < D; i++)
                centroids[k][i] = (proto_t)samples[row][i];
        }
    }
}

} // namespace hdc

#endif // HDC_INITIALIZE_CENTROIDS_HPP
