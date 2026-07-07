/**
 * @file tb_generation.cpp
 * @brief C-sim testbench for the Generation category.
 *
 * Tests: random_hv, gen_levels, rematerialize.
 */
#include <cstdio>
#include <ap_int.h>
#include "generation/random_hv.hpp"
#include "generation/gen_levels.hpp"
#include "generation/rematerialize.hpp"

using hdc::binary_t;

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("  FAIL: %s\n", msg); failures++; } } while (0)

int main() {
    std::printf("== tb_generation ==\n");

    const int D = 32;
    const int F = 4;
    const int L = 8;

    // ---- random_hv<binary, D=32, F=4> : deterministic base codebook ---
    {
        binary_t base1[F][D], base2[F][D];
        hdc::random_hv<binary_t, D, F>(base1, 42);
        hdc::random_hv<binary_t, D, F>(base2, 42);
        bool match = true;
        for (int f = 0; f < F; f++)
            for (int i = 0; i < D; i++)
                if (base1[f][i] != base2[f][i]) match = false;
        CHECK(match, "random_hv with same seed produces identical codebook");
    }

    // ---- gen_levels<binary, D=32, L=8> : continuous item memory -------
    {
        binary_t level[L][D];
        hdc::gen_levels<binary_t, D, L>(level, hdc::LEVEL_LINEAR);
        // Check adjacency: Hamming distance between consecutive levels < between extremes
        int dist_01 = 0, dist_0L = 0;
        for (int i = 0; i < D; i++) {
            if (level[0][i] != level[1][i]) dist_01++;
            if (level[0][i] != level[L-1][i]) dist_0L++;
        }
        CHECK((dist_01 > 0 && dist_01 < dist_0L), "gen_levels: adjacent < extreme Hamming distance");
    }

    // ---- rematerialize<binary, D=32> : row regeneration ----------------
    {
        binary_t base[F][D], rem[D];
        hdc::random_hv<binary_t, D, F>(base, 42);
        // Regenerate row 0 should match base[0]
        hdc::rematerialize<binary_t, D>(0, rem, 42);
        bool match = true;
        for (int i = 0; i < D; i++) if (rem[i] != base[0][i]) match = false;
        CHECK(match, "rematerialize(0) reproduces random_hv row 0");
    }

    std::printf(failures ? "== tb_generation: %d FAILURE(S) ==\n" : "== tb_generation: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
}
