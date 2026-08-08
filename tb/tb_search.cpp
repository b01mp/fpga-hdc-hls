/**
 * @file tb_search.cpp
 * @brief C-sim testbench for the Search category (tested primitive).
 *
 * Covers similarity_search (Hamming/argmin, dot/argmax) and, since the CP
 * restructuring, the class-parallelism EQUIVALENCE property for both
 * similarity_search and convergence_check.
 *
 * Self-contained; returns non-zero on any mismatch.
 */
#include <cstdio>
#include <ap_int.h>
#include "search/similarity_search.hpp"
#include "control/convergence_check.hpp"

using hdc::binary_t;
typedef ap_int<32> sim_t;

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("  FAIL: %s\n", msg); failures++; } } while (0)

// Deterministic pseudo-random source. A fixed LCG rather than rand() so the
// test is reproducible across machines and libc versions -- a correctness test
// that fails only on some hosts is worse than no test.
static unsigned lcg_state = 12345u;
static unsigned lcg() {
    lcg_state = lcg_state * 1103515245u + 12345u;
    return lcg_state >> 16;
}

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

    // ================================================================
    // CLASS-PARALLELISM EQUIVALENCE
    //
    // CP was restructured (loop interchange, query broadcast, per-lane
    // accumulators) because the previous outer-UNROLL form built hardware that
    // did not run in parallel. That restructuring changes the ORDER in which
    // partial results are combined, so the property that has to hold is:
    //
    //     the answer must not depend on CP, or on DP, at all.
    //
    // These cases are chosen to break a careless implementation:
    //   * K = 10 is NOT a multiple of CP=4 or CP=8, so the final group is
    //     partial and the c < K guard has to work.
    //   * D = 37 is NOT a multiple of DP, so the dimension loop has a ragged
    //     tail as well.
    //   * the reference is computed with plain loops HERE in the testbench,
    //     not by calling the primitive at CP=1 -- otherwise a bug common to
    //     every CP would pass unnoticed.
    // ================================================================
    {
        const int Dc = 37;
        const int Kc = 10;
        static binary_t cproto[Kc][Dc];
        static binary_t cq[Dc];

        lcg_state = 12345u;
        for (int k = 0; k < Kc; k++)
            for (int i = 0; i < Dc; i++) cproto[k][i] = (binary_t)(lcg() & 1u);
        for (int i = 0; i < Dc; i++) cq[i] = (binary_t)(lcg() & 1u);

        // Independent reference: Hamming distance, argmin, lowest index on ties.
        int  ref_idx  = 0;
        long ref_best = 0;
        for (int k = 0; k < Kc; k++) {
            long d = 0;
            for (int i = 0; i < Dc; i++) d += (long)(cq[i] ^ cproto[k][i]);
            if (k == 0 || d < ref_best) { ref_best = d; ref_idx = k; }
        }
        std::printf("  reference: class %d at Hamming distance %ld\n", ref_idx, ref_best);

        sim_t sc;
        int   rr;

#define CP_CASE(DPv, CPv)                                                      \
        sc = 0;                                                                \
        rr = hdc::similarity_search<binary_t, sim_t, Dc, Kc, hdc::binary_tag,  \
                                    DPv, CPv>(                                 \
                 cq, cproto, hdc::SIM_HAMMING, hdc::SEARCH_ARGMAX, &sc);       \
        CHECK(rr == ref_idx,                                                   \
              "similarity DP=" #DPv " CP=" #CPv " index == reference");        \
        CHECK((long)sc == ref_best,                                            \
              "similarity DP=" #DPv " CP=" #CPv " score == reference");

        CP_CASE(1, 1)
        CP_CASE(1, 2)
        CP_CASE(1, 4)
        CP_CASE(1, 8)
        CP_CASE(2, 1)
        CP_CASE(2, 4)
        CP_CASE(4, 8)
#undef CP_CASE
    }

    // ---- convergence_check: same equivalence property -------------------
    //
    // convergence_check returns only a bool, so testing it against one
    // threshold would pass even if the internal count were wrong. Bracketing
    // the true count from both sides pins the count exactly: it must be
    // <= exact (true) and NOT <= exact-1 (false).
    {
        const int Dv = 37;
        const int Kv = 10;
        static binary_t nw[Kv][Dv];
        static binary_t od[Kv][Dv];

        lcg_state = 99991u;
        long exact = 0;
        for (int k = 0; k < Kv; k++) {
            for (int i = 0; i < Dv; i++) {
                nw[k][i] = (binary_t)(lcg() & 1u);
                od[k][i] = (binary_t)(lcg() & 1u);
                if (nw[k][i] != od[k][i]) exact++;
            }
        }
        std::printf("  reference: %ld changed elements\n", exact);

#define CONV_CASE(DPv, CPv)                                                    \
        CHECK((hdc::convergence_check<binary_t, Kv, Dv, DPv, CPv>(             \
                   nw, od, exact) == true),                                    \
              "convergence DP=" #DPv " CP=" #CPv " true at threshold==count"); \
        CHECK((hdc::convergence_check<binary_t, Kv, Dv, DPv, CPv>(             \
                   nw, od, exact - 1) == false),                               \
              "convergence DP=" #DPv " CP=" #CPv " false at threshold==count-1");

        CONV_CASE(1, 1)
        CONV_CASE(1, 2)
        CONV_CASE(1, 4)
        CONV_CASE(1, 8)
        CONV_CASE(2, 4)
        CONV_CASE(4, 8)
#undef CONV_CASE

        // Identical inputs must converge at threshold 0 for every CP.
        for (int k = 0; k < Kv; k++)
            for (int i = 0; i < Dv; i++) od[k][i] = nw[k][i];
        CHECK((hdc::convergence_check<binary_t, Kv, Dv, 1, 1>(nw, od, 0) == true),
              "convergence identical CP=1");
        CHECK((hdc::convergence_check<binary_t, Kv, Dv, 1, 8>(nw, od, 0) == true),
              "convergence identical CP=8");
        CHECK((hdc::convergence_check<binary_t, Kv, Dv, 4, 4>(nw, od, 0) == true),
              "convergence identical DP=4 CP=4");
    }

    std::printf(failures ? "== tb_search: %d FAILURE(S) ==\n" : "== tb_search: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
}
