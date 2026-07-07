/**
 * @file tb_aggregation.cpp
 * @brief C-sim testbench for the Aggregation & Update category (tested primitives).
 *
 * Covers the ported-and-verified primitives: bundle, threshold.
 * (normalize/update/cast have reference bodies; add asserted cases as reviewed.)
 *
 * Self-contained; returns non-zero on any mismatch.
 */
#include <cstdio>
#include <ap_int.h>
#include "aggregation/bundle.hpp"
#include "aggregation/threshold.hpp"
#include "aggregation/cast.hpp"

using hdc::binary_t;
typedef ap_int<32> acc_t;

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("  FAIL: %s\n", msg); failures++; } } while (0)

int main() {
    std::printf("== tb_aggregation ==\n");

    const int D = 8;

    // Three binary HVs to bundle.
    binary_t v0[D] = {1,0,1,0,1,0,1,0};
    binary_t v1[D] = {1,1,1,0,0,0,1,1};
    binary_t v2[D] = {1,0,0,0,1,1,1,0};
    // per-index column sums: [3,1,2,0,2,1,3,1]

    acc_t acc[D];
    for (int i = 0; i < D; i++) acc[i] = 0;
    hdc::bundle<binary_t, acc_t, D>(v0, acc);
    hdc::bundle<binary_t, acc_t, D>(v1, acc);
    hdc::bundle<binary_t, acc_t, D>(v2, acc);

    int expect_sum[D] = {3,1,2,0,2,1,3,1};
    bool sum_ok = true;
    for (int i = 0; i < D; i++) if (acc[i] != expect_sum[i]) sum_ok = false;
    CHECK(sum_ok, "bundle accumulates column sums");

    // threshold with count=3 (majority => set iff 2*acc > 3, i.e. acc >= 2).
    binary_t out[D];
    hdc::threshold<acc_t, binary_t, D>(acc, out, 3);
    // acc: [3,1,2,0,2,1,3,1] -> 2*acc vs 3 -> set when acc>=2: [1,0,1,0,1,0,1,0]
    int expect_maj[D] = {1,0,1,0,1,0,1,0};
    bool maj_ok = true;
    for (int i = 0; i < D; i++) if (out[i] != (binary_t)expect_maj[i]) maj_ok = false;
    CHECK(maj_ok, "threshold majority (count=3)");

    // tie behaviour: count=4 => tie when acc==2 (2*acc==4==count).
    hdc::threshold<acc_t, binary_t, D>(acc, out, 4, hdc::TIE_SET_ZERO);
    CHECK(out[2] == 0, "threshold tie -> SET_ZERO");
    hdc::threshold<acc_t, binary_t, D>(acc, out, 4, hdc::TIE_SET_ONE);
    CHECK(out[2] == 1, "threshold tie -> SET_ONE");

    // ---- cast<int, float, D=4> : datatype conversion ---------------------
    {
        const int D = 4;
        int in[D] = {1, 0, 1, 0};
        float out[D];
        hdc::cast<int, float, D>(in, out);
        bool ok = true;
        for (int i = 0; i < D; i++) if ((float)in[i] != out[i]) ok = false;
        CHECK(ok, "cast converts int → float element-wise");
    }

    // ==== Novelty 1: datatype-parametric threshold (collapse op by family) ====

    // ---- threshold<bipolar> : sign(acc) -> {-1,+1} --------------------
    {
        const int Db = 6;
        acc_t bacc[Db] = {5, -3, 0, 12, -1, 2};        // signed bundled sums
        hdc::bipolar_t bout[Db];
        hdc::threshold<acc_t, hdc::bipolar_t, Db, hdc::bipolar_tag>(bacc, bout, 0);
        // sign: >0 -> +1, <0 -> -1, ==0 -> tie (default SET_ZERO => -1 for bipolar)
        int exp[Db] = {1, -1, -1, 1, -1, 1};
        bool ok = true;
        for (int i = 0; i < Db; i++) if (bout[i] != (hdc::bipolar_t)exp[i]) ok = false;
        CHECK(ok, "threshold<bipolar> == sign(acc)");
    }

    // ---- threshold<integer> : passthrough (keep accumulated value) ----
    {
        const int Di = 4;
        acc_t iacc[Di] = {7, -2, 100, 0};
        typedef ap_int<16> i16;
        i16 iout[Di];
        hdc::threshold<acc_t, i16, Di, hdc::integer_tag>(iacc, iout, 0);
        bool ok = true;
        for (int i = 0; i < Di; i++) if (iout[i] != (i16)iacc[i]) ok = false;
        CHECK(ok, "threshold<integer> keeps accumulated value (no binarize)");
    }

    std::printf(failures ? "== tb_aggregation: %d FAILURE(S) ==\n" : "== tb_aggregation: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
}
