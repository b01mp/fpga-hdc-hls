/**
 * @file tb_precision.cpp
 * @brief C-sim gate for the per-stage precision study. Run BEFORE any sweep.
 *
 *     vitis_hls -f scripts/csim_precision.tcl
 *
 * WHAT IT ASSERTS, AND WHY EACH CASE EXISTS
 *
 *  1. RIGHT-SIZED == OVER-PROVISIONED.
 *     Running an application with the derived widths must give byte-identical
 *     predictions to running it with the old hardcoded ap_int<32> score. This
 *     is the claim that right-sizing is FREE: not "close enough", identical.
 *     Checked over many random inputs AND over crafted worst cases, because a
 *     width bug that only fires at the extremes will pass a random-only test.
 *
 *  2. ONE BIT SHORT FAILS -- at the worst case, not necessarily at typical
 *     inputs.
 *     Hamming distance between random binary vectors concentrates near D/2, so
 *     a score one bit too narrow usually looks fine on random data. It only
 *     wraps when the distance approaches D. That is exactly what makes
 *     under-sizing dangerous: it is silently correct on the data you happen to
 *     test with. The crafted case forces the extreme so the failure is
 *     deterministic rather than probabilistic.
 *
 *  3. THE MAJORITY-VOTE OVERFLOW REGRESSION.
 *     thresh_op(binary) used to compute `acc << 1` in acc_t's own width. A
 *     bundle accumulator holds 0..N, so acc can reach N, and 2*N does not fit.
 *     When every bundled hypervector agreed on a dimension the shift wrapped
 *     and the vote returned 0 instead of 1. The unanimity case below reproduces
 *     it deterministically; it fires on image classification (N=16) and genome
 *     (N=8) but not time series (N=6), which is precisely the pattern the
 *     arithmetic predicts.
 *
 * Returns non-zero on any mismatch.
 */
#include <cstdio>
#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "common/hdc_precision.hpp"
#include "application/shared_composition.hpp"

using hdc::binary_t;

static int failures = 0;
#define CHECK(cond, ...) do { if (!(cond)) { \
    std::printf("  FAIL: "); std::printf(__VA_ARGS__); std::printf("\n"); failures++; } } while (0)

// Deterministic LCG -- reproducible across hosts and libc versions.
static unsigned lcg_state = 2463534242u;
static unsigned lcg() { lcg_state = lcg_state * 1103515245u + 12345u; return lcg_state >> 16; }
static binary_t rbit() { return (binary_t)(lcg() & 1u); }

// ---------------------------------------------------------------------------
// Problem shapes. Kept at the tops' own defaults so the testbench exercises
// what actually gets synthesized.
// ---------------------------------------------------------------------------
static const int TD = 1024;    // hypervector dimension, all three applications
static const int IF = 16;      // image: features bundled
static const int IL = 8;       // image: value levels
static const int GW = 8;       // genome: window symbols bundled
static const int GV = 4;       // genome: alphabet
static const int TW = 6;       // time series: window samples bundled
static const int TV = 12;      // time series: levels
static const int NK = 64;      // prototypes / references, all three

static const int TRIALS = 40;

// Storage is static: these are large and csim has an ordinary stack.
static binary_t feat_cb[IF][TD], val_cb[IL][TD], protos[NK][TD];
static ap_uint<3> val_idx[IF];
static binary_t sym_cb[GV][TD];
static ap_uint<4> sym_idx[GW];
static binary_t ts_cb[TV][TD];
static ap_uint<4> ts_idx[TW];
static binary_t query_buf[TD], ref_buf[NK][TD];

// ---------------------------------------------------------------------------
// One run of each application, with the intermediate widths as template
// parameters so the same source is exercised at every precision.
// ---------------------------------------------------------------------------
template <int ACCB, int SIMB>
static int run_image() {
    binary_t q[TD];
    hdc_app::encode_feature_value_query<TD, IF, IL, 1, ap_uint<ACCB> >(
        feat_cb, val_cb, val_idx, q);
    return hdc_app::search_binary_references<TD, NK, 1, 1, ap_int<SIMB> >(q, protos);
}

template <int ACCB, int SIMB>
static int run_genome() {
    binary_t q[TD];
    hdc_app::encode_ordered_window_query<TD, GW, GV, 1, ap_uint<ACCB> >(
        sym_cb, sym_idx, q);
    return hdc_app::search_binary_references<TD, NK, 1, 1, ap_int<SIMB> >(q, protos);
}

template <int ACCB, int SIMB>
static int run_ts() {
    binary_t q[TD];
    hdc_app::encode_ordered_window_query<TD, TW, TV, 1, ap_uint<ACCB> >(
        ts_cb, ts_idx, q);
    return hdc_app::search_binary_references<TD, NK, 1, 1, ap_int<SIMB> >(q, protos);
}

static void randomize_all() {
    for (int f = 0; f < IF; f++) for (int d = 0; d < TD; d++) feat_cb[f][d] = rbit();
    for (int l = 0; l < IL; l++) for (int d = 0; d < TD; d++) val_cb[l][d] = rbit();
    for (int v = 0; v < GV; v++) for (int d = 0; d < TD; d++) sym_cb[v][d] = rbit();
    for (int v = 0; v < TV; v++) for (int d = 0; d < TD; d++) ts_cb[v][d]  = rbit();
    for (int k = 0; k < NK; k++) for (int d = 0; d < TD; d++) protos[k][d] = rbit();
    for (int f = 0; f < IF; f++) val_idx[f] = (ap_uint<3>)(lcg() % IL);
    for (int w = 0; w < GW; w++) sym_idx[w] = (ap_uint<4>)(lcg() % GV);
    for (int w = 0; w < TW; w++) ts_idx[w]  = (ap_uint<4>)(lcg() % TV);
}

int main() {
    std::printf("== tb_precision ==\n");
    std::printf("   D=%d  K=%d   image F=%d  genome W=%d  ts W=%d\n",
                TD, NK, IF, GW, TW);

    const int SIM_RULE = hdc::hamming_score_bits<TD>::value;      // 12 at D=1024
    const int ACC_I    = hdc::bundle_acc_bits<IF>::value;         // 5
    const int ACC_G    = hdc::bundle_acc_bits<GW>::value;         // 4
    const int ACC_T    = hdc::bundle_acc_bits<TW>::value;         // 3
    std::printf("   derived widths: score=%d  acc(image)=%d acc(genome)=%d acc(ts)=%d\n\n",
                SIM_RULE, ACC_I, ACC_G, ACC_T);

    // =====================================================================
    // CASE 1 -- right-sized is IDENTICAL to over-provisioned, over many inputs
    // =====================================================================
    std::printf("-- case 1: right-sized == ap_int<32>, %d random trials --\n", TRIALS);
    {
        int mism_i = 0, mism_g = 0, mism_t = 0;
        for (int t = 0; t < TRIALS; t++) {
            randomize_all();
            if (run_image <5, 12>() != run_image <5, 32>()) mism_i++;
            if (run_genome<4, 12>() != run_genome<4, 32>()) mism_g++;
            if (run_ts    <3, 12>() != run_ts    <3, 32>()) mism_t++;
        }
        CHECK(mism_i == 0, "image: %d/%d trials differ between 12-bit and 32-bit score",
              mism_i, TRIALS);
        CHECK(mism_g == 0, "genome: %d/%d trials differ", mism_g, TRIALS);
        CHECK(mism_t == 0, "time series: %d/%d trials differ", mism_t, TRIALS);
        std::printf("   image %d/%d  genome %d/%d  ts %d/%d mismatches\n",
                    mism_i, TRIALS, mism_g, TRIALS, mism_t, TRIALS);
    }

    // =====================================================================
    // CASE 2 -- the score at its extreme. Worst case, not random.
    //
    // query = all ones. reference 0 = all zeros  -> Hamming distance D (the
    // MAXIMUM). reference 1 = all ones -> distance 0 (the true argmin).
    //
    // A right-sized signed score holds D and returns 1. One bit short, D wraps
    // NEGATIVE, becomes the smallest value seen, and argmin returns 0 -- the
    // furthest reference reported as the nearest.
    // =====================================================================
    std::printf("\n-- case 2: score at the extreme (distance == D) --\n");
    {
        for (int d = 0; d < TD; d++) query_buf[d] = (binary_t)1;
        for (int d = 0; d < TD; d++) { ref_buf[0][d] = (binary_t)0; ref_buf[1][d] = (binary_t)1; }
        for (int k = 2; k < NK; k++) for (int d = 0; d < TD; d++) ref_buf[k][d] = (binary_t)(d & 1);

        const int wide  = hdc_app::search_binary_references<TD, NK, 1, 1, ap_int<32> >(query_buf, ref_buf);
        const int right = hdc_app::search_binary_references<TD, NK, 1, 1, ap_int<12> >(query_buf, ref_buf);
        const int shortb= hdc_app::search_binary_references<TD, NK, 1, 1, ap_int<11> >(query_buf, ref_buf);

        std::printf("   ap_int<32> -> %d   ap_int<%d> -> %d   ap_int<%d> -> %d\n",
                    wide, SIM_RULE, right, SIM_RULE - 1, shortb);
        CHECK(wide == 1, "over-provisioned score should find reference 1 (distance 0), got %d", wide);
        CHECK(right == wide, "right-sized score (%d bits) must match ap_int<32>: %d vs %d",
              SIM_RULE, right, wide);
        CHECK(shortb != wide,
              "one bit short (%d) should WRAP at distance D and mispredict, but matched (%d)",
              SIM_RULE - 1, shortb);
    }

    // =====================================================================
    // CASE 3 -- majority-vote overflow regression.
    //
    // Force UNANIMITY: every feature hypervector identical, every value
    // hypervector identical, so every bound hypervector is identical and every
    // dimension accumulates to exactly N. That is the one input where
    // `acc << 1` overflowed an acc_t sized to hold only N.
    //
    // With the fix, the query is all ones and the search returns the all-ones
    // reference. Without it the query came out all zeros and the search
    // returned the all-zeros reference instead.
    // =====================================================================
    std::printf("\n-- case 3: majority vote under unanimity (acc == N) --\n");
    {
        for (int f = 0; f < IF; f++) for (int d = 0; d < TD; d++) feat_cb[f][d] = (binary_t)1;
        for (int l = 0; l < IL; l++) for (int d = 0; d < TD; d++) val_cb[l][d]  = (binary_t)0;
        for (int f = 0; f < IF; f++) val_idx[f] = (ap_uint<3>)0;
        // bind(1,0) = 1 for every feature -> every dimension accumulates to IF.

        for (int d = 0; d < TD; d++) { protos[0][d] = (binary_t)0; protos[1][d] = (binary_t)1; }
        for (int k = 2; k < NK; k++) for (int d = 0; d < TD; d++) protos[k][d] = (binary_t)(d & 1);

        const int got = run_image<5, 32>();
        std::printf("   image, acc=ap_uint<5> (holds 0..%d), unanimous acc=%d -> class %d\n",
                    (1 << ACC_I) - 1, IF, got);
        CHECK(got == 1,
              "unanimous 1s must threshold to an all-ones query and match reference 1, got %d "
              "(a 0 here means acc<<1 wrapped inside thresh_op)", got);

        // Genome: same shape, N=8 with ap_uint<4>.
        for (int v = 0; v < GV; v++) for (int d = 0; d < TD; d++) sym_cb[v][d] = (binary_t)1;
        for (int w = 0; w < GW; w++) sym_idx[w] = (ap_uint<4>)0;
        // permute of an all-ones vector is all ones, so every dimension sums to GW.
        const int gotg = run_genome<4, 32>();
        std::printf("   genome, acc=ap_uint<4> (holds 0..%d), unanimous acc=%d -> class %d\n",
                    (1 << ACC_G) - 1, GW, gotg);
        CHECK(gotg == 1, "genome unanimity must give an all-ones query, got %d", gotg);

        // Time series: N=6 in ap_uint<3> under the derived rule.
        for (int v = 0; v < TV; v++) for (int d = 0; d < TD; d++) ts_cb[v][d] = (binary_t)1;
        for (int w = 0; w < TW; w++) ts_idx[w] = (ap_uint<4>)0;
        const int gott = run_ts<3, 32>();
        std::printf("   time series, acc=ap_uint<3> (holds 0..%d), unanimous acc=%d -> class %d\n",
                    (1 << ACC_T) - 1, TW, gott);
        CHECK(gott == 1, "time series unanimity must give an all-ones query, got %d", gott);
    }

    std::printf(failures ? "\n== tb_precision: %d FAILURE(S) ==\n"
                         : "\n== tb_precision: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
}
