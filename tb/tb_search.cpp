/**
 * @file tb_search.cpp
 * @brief C-sim testbench for the Search category (tested primitive).
 *
 * Covers the ported-and-verified primitive: similarity_search (Hamming, argmax).
 * Self-contained; returns non-zero on any mismatch.
 */
#include <cstdio>
#include <ap_int.h>
#include "search/similarity_search.hpp"

using hdc::binary_t;
typedef ap_int<32> sim_t;

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("  FAIL: %s\n", msg); failures++; } } while (0)

int main() {
    std::printf("== tb_search ==\n");

    const int D = 8;
    const int K = 3;
    binary_t proto[K][D] = {
        {0,0,0,0,0,0,0,0},   // class 0
        {1,1,1,1,0,0,0,0},   // class 1
        {1,1,1,1,1,1,1,1},   // class 2
    };

    // Exact match to class 1.
    binary_t q1[D] = {1,1,1,1,0,0,0,0};
    sim_t dist = -1;
    int r1 = hdc::similarity_search<binary_t, sim_t, D, K>(q1, proto, hdc::SIM_HAMMING, hdc::SEARCH_ARGMAX, &dist);
    CHECK(r1 == 1, "exact match -> class 1");
    CHECK(dist == 0, "exact match -> Hamming distance 0");

    // One-bit off class 2 (flip a single bit) -> should still pick class 2.
    binary_t q2[D] = {1,1,1,1,1,1,1,0};
    int r2 = hdc::similarity_search<binary_t, sim_t, D, K>(q2, proto, hdc::SIM_HAMMING, hdc::SEARCH_ARGMAX);
    CHECK(r2 == 2, "1-bit off class 2 -> class 2");

    // All zeros -> class 0.
    binary_t q0[D] = {0,0,0,0,0,0,0,0};
    int r0 = hdc::similarity_search<binary_t, sim_t, D, K>(q0, proto);
    CHECK(r0 == 0, "all-zeros -> class 0");

    // ==== Novelty 1: datatype-parametric similarity (metric + direction by family) ====

    // ---- similarity_search<bipolar> : dot product, argmax --------------
    {
        const int Db = 8;
        const int Kb = 3;
        hdc::bipolar_t bproto[Kb][Db] = {
            {-1,-1,-1,-1,-1,-1,-1,-1},   // class 0
            { 1, 1, 1, 1,-1,-1,-1,-1},   // class 1
            { 1, 1, 1, 1, 1, 1, 1, 1},   // class 2
        };
        hdc::bipolar_t bq[Db] = {1,1,1,1,-1,-1,-1,-1};       // == class 1
        sim_t score = 0;
        int rb = hdc::similarity_search<hdc::bipolar_t, sim_t, Db, Kb, hdc::bipolar_tag>(
                     bq, bproto, hdc::SIM_DOT, hdc::SEARCH_ARGMAX, &score);
        CHECK(rb == 1, "similarity<bipolar> dot/argmax -> class 1");
        CHECK(score == 8, "similarity<bipolar> exact match dot == D");
    }

    // ---- similarity_search<fixed> : dot product, argmax ----------------
    {
        const int Df = 4;
        const int Kf = 2;
        typedef ap_fixed<16,8> fx;
        fx fproto[Kf][Df] = { {1.0,1.0,0.0,0.0}, {0.0,0.0,1.0,1.0} };
        fx fq[Df] = {0.0, 0.0, 1.0, 1.0};                    // == class 1
        int rf = hdc::similarity_search<fx, fx, Df, Kf, hdc::fixed_tag>(
                     fq, fproto, hdc::SIM_DOT, hdc::SEARCH_ARGMAX);
        CHECK(rf == 1, "similarity<fixed> dot/argmax -> class 1");
    }

    std::printf(failures ? "== tb_search: %d FAILURE(S) ==\n" : "== tb_search: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
}
