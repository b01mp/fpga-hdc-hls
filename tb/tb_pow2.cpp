/**
 * @file tb_pow2.cpp
 * @brief C-sim proof for the power-of-two (pow2) datatype family.
 *
 * A pow2 element is a SIGNED power of two: 1 sign bit + POW2_EXP_BITS exponent
 * bits, value = (-1)^sign * 2^k. Every claim the library makes about that
 * representation is asserted here:
 *
 *   1  pack/unpack round-trip over the whole exponent range, both signs
 *   2  decode gives exactly +/-2^k
 *   3  encode of an exact power of two returns that exponent
 *   4  encode rounds to the NEAREST power of two (with the tie going up)
 *   5  encode(0) returns +2^0 -- the documented quantisation floor
 *   6  pack SATURATES the exponent; it must never wrap
 *   7  bind is a multiply: signs XOR, exponents add
 *   8  bind saturates rather than wrapping
 *   9  random_hv draws only +/-2^0, and draws BOTH signs
 *  10  gen_levels draws only +/-2^0, both signs, and keeps graded distance
 *  11  bundle decodes before accumulating (it must not sum exponents)
 *  12  threshold re-encodes an accumulator instead of casting it
 *  13  similarity_search ranks prototypes by true dot product
 *
 * Tests 11-13 are the ones that would have silently passed with the OLD code
 * while producing wrong numbers, so they matter most.
 */
#include <cstdio>
#include <cstdlib>
#include "common/hdc_types.hpp"
#include "encoding/bind.hpp"
#include "aggregation/bundle.hpp"
#include "aggregation/threshold.hpp"
#include "search/similarity_search.hpp"
#include "generation/random_hv.hpp"
#include "generation/gen_levels.hpp"

typedef ap_int<64> wide_t;      // headroom for decoded products
typedef ap_int<32> acc32_t;     // matches the accumulator width in top_datatype.cpp

#define TB_D 256
#define TB_F 4
#define TB_L 5
#define TB_K 4

static int fails = 0;

static void chk(bool cond, const char *what, long long got, long long want) {
    if (!cond) {
        printf("  FAIL %-42s got %lld, want %lld\n", what, got, want);
        fails++;
    }
}

// Reference value of a pow2 element, computed in plain C++.
static long long ref_val(hdc::pow2_t e) {
    long long m = 1LL << (int)hdc::pow2_exp(e);
    return hdc::pow2_sign(e) ? -m : m;
}

static hdc::pow2_t P(bool neg, int k) { return hdc::pow2_pack(neg, k); }

// ---------------------------------------------------------------- 1, 2, 6 ---
static void test_pack_decode() {
    printf("[1,2,6] pack / decode / saturation\n");
    for (int k = 0; k <= hdc::POW2_EXP_MAX; k++) {
        for (int s = 0; s < 2; s++) {
            hdc::pow2_t e = P(s != 0, k);
            chk((int)hdc::pow2_exp(e) == k, "exponent round-trip", (int)hdc::pow2_exp(e), k);
            chk(hdc::pow2_sign(e) == (s != 0), "sign round-trip", hdc::pow2_sign(e), s);
            if (k < 62) {
                wide_t d = hdc::pow2_decode<wide_t>(e);
                long long want = (s ? -1LL : 1LL) << k;
                chk((long long)d == want, "decode == +/-2^k", (long long)d, want);
            }
        }
    }
    // saturation, not wraparound: 40 & 31 would be 8, which must NOT happen
    hdc::pow2_t sat = P(false, 40);
    chk((int)hdc::pow2_exp(sat) == hdc::POW2_EXP_MAX,
        "pack saturates k=40", (int)hdc::pow2_exp(sat), hdc::POW2_EXP_MAX);
    hdc::pow2_t neg = P(true, -3);
    chk((int)hdc::pow2_exp(neg) == 0, "pack clamps k<0", (int)hdc::pow2_exp(neg), 0);
}

// ------------------------------------------------------------------- 3,4,5 ---
static void test_encode() {
    printf("[3,4,5] encode: exact, nearest-rounding, zero floor\n");
    // exact powers of two, both signs
    for (int k = 0; k <= 20; k++) {
        wide_t v = (wide_t)(1LL << k);
        hdc::pow2_t e = hdc::pow2_encode<wide_t>(v);
        chk((int)hdc::pow2_exp(e) == k && !hdc::pow2_sign(e),
            "encode(+2^k)", (int)hdc::pow2_exp(e), k);
        hdc::pow2_t en = hdc::pow2_encode<wide_t>((wide_t)(-(1LL << k)));
        chk((int)hdc::pow2_exp(en) == k && hdc::pow2_sign(en),
            "encode(-2^k)", (int)hdc::pow2_exp(en), k);
    }
    // round to nearest; ties go up.  |3-2|=|3-4| -> 4 ;  5 -> 4 ;  6,7 -> 8
    const long long in[]   = {1, 2, 3, 4, 5, 6, 7, 9, 11, 12, 100, 200};
    const int       want[] = {0, 1, 2, 2, 2, 3, 3, 3,  3,  4,   7,   8};
    for (int i = 0; i < 12; i++) {
        hdc::pow2_t e = hdc::pow2_encode<wide_t>((wide_t)in[i]);
        chk((int)hdc::pow2_exp(e) == want[i], "encode rounds to nearest",
            (int)hdc::pow2_exp(e), want[i]);
    }
    // documented quantisation floor: no zero in the family
    hdc::pow2_t z = hdc::pow2_encode<wide_t>((wide_t)0);
    chk(ref_val(z) == 1, "encode(0) == +2^0 (floor)", ref_val(z), 1);
}

// --------------------------------------------------------------------- 7,8 ---
static void test_bind() {
    printf("[7,8] bind: sign XOR, exponent ADD\n");
    for (int ka = 0; ka <= 8; ka++) {
        for (int kb = 0; kb <= 8; kb++) {
            for (int sa = 0; sa < 2; sa++) {
                for (int sb = 0; sb < 2; sb++) {
                    hdc::pow2_t a = P(sa != 0, ka), b = P(sb != 0, kb);
                    hdc::pow2_t r = hdc::bind_op(a, b, hdc::pow2_tag());
                    chk(ref_val(r) == ref_val(a) * ref_val(b),
                        "value(bind) == value(a)*value(b)",
                        ref_val(r), ref_val(a) * ref_val(b));
                }
            }
        }
    }
    // exponents that would overflow the field must saturate, not wrap
    hdc::pow2_t big = hdc::bind_op(P(false, 20), P(false, 20), hdc::pow2_tag());
    chk((int)hdc::pow2_exp(big) == hdc::POW2_EXP_MAX,
        "bind saturates on overflow", (int)hdc::pow2_exp(big), hdc::POW2_EXP_MAX);
}

// -------------------------------------------------------------------- 9,10 ---
static hdc::pow2_t cb[TB_F][TB_D];
static hdc::pow2_t lv[TB_L][TB_D];

static void test_generation() {
    printf("[9,10] random_hv / gen_levels draw +/-2^0 with both signs\n");
    hdc::random_hv<hdc::pow2_t, TB_D, TB_F, hdc::pow2_tag>(cb);
    int neg = 0;
    for (int f = 0; f < TB_F; f++)
        for (int d = 0; d < TB_D; d++) {
            long long v = ref_val(cb[f][d]);
            chk(v == 1 || v == -1, "random_hv element is +/-1", v, 1);
            if (v == -1) neg++;
        }
    chk(neg > 0, "random_hv produced negatives", neg, 1);

    hdc::gen_levels<hdc::pow2_t, TB_D, TB_L, hdc::pow2_tag>(lv);
    int lneg = 0;
    for (int l = 0; l < TB_L; l++)
        for (int d = 0; d < TB_D; d++) {
            long long v = ref_val(lv[l][d]);
            chk(v == 1 || v == -1, "gen_levels element is +/-1", v, 1);
            if (v == -1) lneg++;
        }
    chk(lneg > 0, "gen_levels produced negatives", lneg, 1);

    int diff = 0;
    for (int d = 0; d < TB_D; d++) if (lv[0][d] != lv[TB_L - 1][d]) diff++;
    printf("      level0 vs level%d differ in %d/%d dims (expect ~%d)\n",
           TB_L - 1, diff, TB_D, TB_D / 2);
    chk(diff > TB_D / 4 && diff < (3 * TB_D) / 4, "graded level distance", diff, TB_D / 2);
}

// ----------------------------------------------------------------- 11 ,12 ---
static hdc::pow2_t bv[TB_D];
static acc32_t     acc[TB_D];
static hdc::pow2_t out[TB_D];

static void test_bundle_threshold() {
    printf("[11,12] bundle decodes before accumulating; threshold re-encodes\n");
    // dim i holds +2^(i%5); bundling it 3 times must give 3*2^(i%5),
    // NOT 3*(i%5) (which is what summing raw exponents would produce).
    for (int i = 0; i < TB_D; i++) { bv[i] = P(false, i % 5); acc[i] = 0; }
    for (int rep = 0; rep < 3; rep++)
        hdc::bundle<hdc::pow2_t, acc32_t, TB_D, 1, hdc::pow2_tag>(bv, acc);
    for (int i = 0; i < TB_D; i++) {
        long long want = 3LL * (1LL << (i % 5));
        chk((long long)acc[i] == want, "bundle accumulates VALUES", (long long)acc[i], want);
    }
    // threshold re-encodes: 3*2^k rounds to 2^(k+2) (since 3 -> 4)
    hdc::threshold<acc32_t, hdc::pow2_t, TB_D, hdc::pow2_tag, 1>(acc, out, 3);
    for (int i = 0; i < TB_D; i++) {
        long long want = 1LL << ((i % 5) + 2);
        chk(ref_val(out[i]) == want, "threshold encodes nearest 2^k", ref_val(out[i]), want);
    }
    // negatives keep their sign through the round trip
    for (int i = 0; i < TB_D; i++) acc[i] = (acc32_t)(-(1 << (i % 4)));
    hdc::threshold<acc32_t, hdc::pow2_t, TB_D, hdc::pow2_tag, 1>(acc, out, 1);
    for (int i = 0; i < TB_D; i++) {
        long long want = -(1LL << (i % 4));
        chk(ref_val(out[i]) == want, "threshold keeps sign", ref_val(out[i]), want);
    }
}

// --------------------------------------------------------------------- 13 ---
static hdc::pow2_t q[TB_D];
static hdc::pow2_t proto[TB_K][TB_D];

static void test_similarity() {
    printf("[13] similarity_search ranks by true dot product\n");
    // All elements are +/-2^0, so pow2 behaves exactly like bipolar here and the
    // dot product is easy to compute by hand. Prototype c agrees with the query
    // on the first (TB_D - c*16) dims, so class 0 must win.
    for (int i = 0; i < TB_D; i++) q[i] = P((i % 3) == 0, 0);
    for (int c = 0; c < TB_K; c++) {
        int flip_from = TB_D - c * 16;
        for (int i = 0; i < TB_D; i++) {
            bool s = hdc::pow2_sign(q[i]);
            if (i >= flip_from) s = !s;              // disagree on the tail
            proto[c][i] = P(s, 0);
        }
    }
    long long best = -(1LL << 62); int best_c = -1;
    for (int c = 0; c < TB_K; c++) {
        long long dot = 0;
        for (int i = 0; i < TB_D; i++) dot += ref_val(q[i]) * ref_val(proto[c][i]);
        if (dot > best) { best = dot; best_c = c; }
        printf("      class %d: reference dot = %lld\n", c, dot);
    }
    int got = hdc::similarity_search<hdc::pow2_t, ap_int<32>, TB_D, TB_K,
                                     hdc::pow2_tag, 1, 1>(q, proto);
    chk(got == best_c, "argmax over pow2 dot product", got, best_c);
}

int main() {
    printf("=== pow2 datatype family ===\n");
    printf("POW2_EXP_BITS=%d  POW2_EXP_MAX=%d  element width=%d bits\n\n",
           hdc::POW2_EXP_BITS, hdc::POW2_EXP_MAX, hdc::POW2_EXP_BITS + 1);
    test_pack_decode();
    test_encode();
    test_bind();
    test_generation();
    test_bundle_threshold();
    test_similarity();
    if (fails) printf("\nFAIL: %d issue(s)\n", fails);
    else       printf("\nPASS: pow2 representation, ops, generation and search all correct\n");
    return fails ? 1 : 0;
}
