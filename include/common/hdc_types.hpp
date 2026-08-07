/**
 * @file hdc_types.hpp
 * @brief Shared datatypes and mode enums for the FPGA-HDC primitive library.
 *
 * The library is datatype-parametric: every primitive takes its element/accum/
 * similarity datatype as a C++ `typename` template argument, and its sizes
 * (hv_dim, num_features, num_levels, num_prototypes, ...) as `int` template
 * arguments. That is how the APPLICATION parameters from the parameter table are
 * "wired as inputs" to each function -- no application-specific constants live
 * inside a primitive (compare the emg_hdc baseline, which fixed these via a
 * config header). Nothing here forces a width; callers pick the concrete type.
 *
 * The enums below are the *mode* application-parameters (level_mode,
 * similarity_metric, search_mode, update_mode, ...): passed as ordinary function
 * arguments so a testbench can exercise each setting.
 */

#ifndef HDC_TYPES_HPP
#define HDC_TYPES_HPP

#include <ap_int.h>
#include <ap_fixed.h>

namespace hdc {

// ---- Convenience element aliases (callers may also pass any ap_* type) ------
typedef ap_uint<1> binary_t;     // element_bits = 1  (binary HV element, {0,1})
typedef ap_int<2>  bipolar_t;    // bipolar element {-1, +1}
// fixed-point / integer elements are e.g. ap_fixed<..> or ap_int<W>.
// Power-of-two elements are `pow2_t`, defined below.

// ---- Datatype-family tags: compile-time op selection via tag dispatch --------
//   Each datatype-parametric primitive (bind, bundle, threshold,
//   similarity_search, update) overloads a small op-helper on one of these tags.
//   Instantiating a primitive with a tag selects that op at COMPILE time (no
//   runtime branch / mux) -- this is the "datatype-parametric" novelty:
//   bind<...,binary_tag> is an XOR gate, bind<...,bipolar_tag> is a multiply,
//   bind<...,pow2_tag> is an adder. (CGR intentionally excluded.)
struct binary_tag  {};   // {0,1}           bind=XOR,  threshold=majority, sim=Hamming
struct bipolar_tag {};   // {-1,+1}         bind=mul,  threshold=sign,     sim=dot
struct fixed_tag   {};   // ap_fixed reals  bind=mul,  threshold=passthru, sim=dot
struct pow2_tag    {};   // +/-2^k          bind=XOR sign + ADD exp,       sim=dot (shift)
struct integer_tag {};   // ap_int<W>       bind=mul,  threshold=passthru, sim=dot

// ---- Memory-space tags: on-chip indexed read vs off-chip HBM burst -----------
struct onchip_tag  {};   // codebook in BRAM/URAM -> gather
struct offchip_tag {};   // codebook in HBM/DDR   -> hbm_gather

// ---- Compile-time family predicate (used by static_assert guards) -----------
template <typename F> struct is_pow2_family { static const bool value = false; };
template <>           struct is_pow2_family<pow2_tag> { static const bool value = true; };

// =============================================================================
// POWER-OF-TWO ELEMENTS
// =============================================================================
// A pow2 element is a SIGNED power of two, packed as
//
//      bit  POW2_EXP_BITS      : sign  (1 = negative)
//      bits POW2_EXP_BITS-1..0 : exponent k, unsigned
//      value = (-1)^sign * 2^k
//
// WHY SIGNED. The earlier definition ("an ap_uint holding an exponent k") is
// unusable in HDC: bundling, dot products and sign-thresholding all need signed
// values, and an unsigned type silently wrapped every negative draw.
//
// WHY 5 EXPONENT BITS. The reference element in a BioHD-style library is a sum
// of P bundled +/-1 sequence hypervectors; BioHD (ISCA'22) evaluates up to
// P = 1e9 and therefore stores its library at 32-bit precision. k in [0,31]
// covers |value| up to 2^31, i.e. the same dynamic range as int32 -- in 6 bits
// instead of 32. At D=10240, K=256 that is 1.9 MB instead of 10 MB, which is the
// difference between fitting in on-chip memory and not.
//
// HARDWARE PAYOFF. Multiply becomes XOR(sign) + ADD(exponent); multiply-by-
// element in similarity becomes a variable shift. No DSPs on either path.
//
// KNOWN LIMITATION. A signed power of two cannot represent exactly zero: the
// smallest magnitude is 2^0 = 1. pow2_encode() maps 0 to +1. For HDC element
// values this is harmless (elements are never meaningfully zero), but it is a
// real quantisation floor and must be accounted for in any accuracy study.
// -----------------------------------------------------------------------------
static const int POW2_EXP_BITS = 5;                       // exponent field width
static const int POW2_EXP_MAX  = (1 << POW2_EXP_BITS) - 1; // k in [0, 31]

typedef ap_uint<POW2_EXP_BITS + 1> pow2_t;                // 1 sign + 5 exponent

inline ap_uint<POW2_EXP_BITS> pow2_exp(pow2_t e) {
    return e.range(POW2_EXP_BITS - 1, 0);
}
inline bool pow2_sign(pow2_t e) {
    return (bool)e[POW2_EXP_BITS];
}
inline pow2_t pow2_pack(bool neg, int k) {
    if (k < 0)             k = 0;
    if (k > POW2_EXP_MAX)  k = POW2_EXP_MAX;              // saturate, never wrap
    pow2_t r = 0;
    r.range(POW2_EXP_BITS - 1, 0) = (ap_uint<POW2_EXP_BITS>)k;
    r[POW2_EXP_BITS] = neg;
    return r;
}

// Decode to a linear value in acc_t: a shift plus a conditional negate.
template <typename acc_t>
inline acc_t pow2_decode(pow2_t e) {
    acc_t mag = (acc_t)(((acc_t)1) << (int)pow2_exp(e));
    return pow2_sign(e) ? (acc_t)(-mag) : mag;
}

// Encode a linear value as the NEAREST signed power of two.
//
// The exponent is the position of the magnitude's most significant set bit,
// found by a 5-step BINARY SEARCH -- about five levels of logic. An earlier
// version walked 31 successive magnitude comparisons (`m < 2*p`) instead, which
// synthesised to a 31-deep chain of 32-bit comparators per lane: 36,140 LUT and
// 48,901 FF for threshold at DP=8, roughly 90x the next-worst family. Testing a
// bit position costs one LUT input; comparing two 32-bit numbers does not.
//
// Values at or above 2^POW2_EXP_MAX saturate immediately, so the search only
// ever runs on the low bits.
//
// Rounding: step up when m is closer to 2^(k+1) than to 2^k, i.e. 2m >= 3*2^k.
// Ties round up. Uses two adds and one comparator.
template <typename acc_t>
inline pow2_t pow2_encode(acc_t v) {
    bool  neg = (v < 0);
    acc_t a   = neg ? (acc_t)(-v) : v;
    if (a == 0) return pow2_pack(false, 0);               // quantisation floor: +1

    ap_uint<64> m64 = (ap_uint<64>)a;
    if (m64 >> POW2_EXP_MAX) return pow2_pack(neg, POW2_EXP_MAX);   // saturate
    ap_uint<32> m = (ap_uint<32>)m64;

    ap_uint<32> t = m;
    int k = 0;
    if (t >> 16) { k += 16; t >>= 16; }
    if (t >> 8)  { k += 8;  t >>= 8;  }
    if (t >> 4)  { k += 4;  t >>= 4;  }
    if (t >> 2)  { k += 2;  t >>= 2;  }
    if (t >> 1)  { k += 1; }
    // invariant here: 2^k <= m < 2^(k+1)

    if (k < POW2_EXP_MAX) {
        ap_uint<34> p = ((ap_uint<34>)1) << k;
        if ((((ap_uint<34>)m) << 1) >= (ap_uint<34>)(p + p + p)) k++;
    }
    return pow2_pack(neg, k);
}

// Product of two pow2 elements: signs XOR, exponents ADD (2^a * 2^b = 2^(a+b)).
inline pow2_t pow2_bind(pow2_t a, pow2_t b) {
    int k = (int)pow2_exp(a) + (int)pow2_exp(b);
    return pow2_pack(pow2_sign(a) ^ pow2_sign(b), k);     // pow2_pack saturates k
}

// ---- Mode application-parameters (passed as function arguments) -------------

// threshold_tie: how threshold() breaks an exact count/2 tie.
enum tie_policy_t { TIE_SET_ZERO = 0, TIE_SET_ONE = 1 };

// level_mode: inter-level correlation policy for gen_levels().
enum level_mode_t { LEVEL_LINEAR = 0, LEVEL_APPROX_LINEAR = 1, LEVEL_THERMOMETER = 2 };

// similarity_metric: distance/similarity datapath in similarity_search().
enum sim_metric_t { SIM_HAMMING = 0, SIM_COSINE = 1, SIM_DOT = 2 };

// search_mode: how a winner is picked from the per-class scores.
enum search_mode_t { SEARCH_ARGMAX = 0, SEARCH_ARGMIN = 1, SEARCH_TOPK = 2, SEARCH_THRESHOLDED = 3 };

// update_mode: prototype state update rule in update().
enum update_mode_t { UPDATE_ADD = 0, UPDATE_ADD_SUB = 1, UPDATE_PERCEPTRON = 2 };

// centroid_init_mode: seeding policy for initialize_centroids().
enum centroid_init_t { CINIT_RANDOM = 0, CINIT_SAMPLE = 1 };

} // namespace hdc

#endif // HDC_TYPES_HPP
