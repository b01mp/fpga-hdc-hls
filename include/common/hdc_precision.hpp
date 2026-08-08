/**
 * @file hdc_precision.hpp   (Common)
 * @brief Compile-time width rules for the per-stage intermediate types.
 *
 * WHY THIS FILE EXISTS
 *   An HDC pipeline carries several intermediates, and each one has a
 *   DIFFERENT correct width:
 *
 *     bundle accumulator   holds 0..N, where N is the number of hypervectors
 *                          summed  ->  needs bits_for(N)
 *     similarity score     holds 0..D for Hamming over D dimensions
 *                          ->  needs bits_for(D) (+1 for the sign, since the
 *                              search accumulator is signed)
 *
 *   These are not the same number and they do not move together. A pipeline
 *   with D = 10240 and N = 16 wants a 5-bit accumulator and a 15-bit score.
 *   A single global "precision" setting cannot express that: set it wide
 *   enough for the score and the accumulator wastes 10 bits per dimension;
 *   set it narrow for the accumulator and the score wraps.
 *
 *   Before this header, the library already followed the accumulator rule --
 *   `typedef ap_uint<5> app_acc_t;  // ceil(log2(APP_F + 1))` -- as a hand
 *   computed constant with the rule in a comment. The score did not: every
 *   application hardcoded `ap_int<32>` regardless of D. At the sizes those
 *   applications actually run, 32 is roughly 4x wider than necessary.
 *
 *   Putting both rules here makes them checkable, keeps them consistent across
 *   applications, and makes them re-derive automatically when D or N changes,
 *   which a hand-computed constant does not.
 *
 * WHY WIDTHS MATTER MORE THAN "PRECISION" USUALLY DOES
 *   ap_int and ap_uint WRAP. They do not saturate. An accumulator one bit too
 *   narrow does not lose a little accuracy -- it silently produces a value from
 *   the wrong end of the number line, and the argmin picks a different class.
 *   So for these integer intermediates there is no accuracy/area trade-off
 *   curve at all: there is a threshold, below which the result is wrong and
 *   above which the extra bits buy nothing. That is the opposite of the
 *   ELEMENT datatype, where narrowing degrades smoothly.
 *
 *   Both facts are true in the same pipeline, which is the whole argument for
 *   sizing stages independently.
 *
 * USAGE
 *     #include "common/hdc_precision.hpp"
 *
 *     typedef ap_uint<hdc::bundle_acc_bits<APP_F>::value> app_acc_t;
 *     typedef ap_int <hdc::hamming_score_bits<APP_D>::value> app_sim_t;
 *
 *   Both are compile-time constants, so they are usable as template arguments
 *   and cost nothing at run time.
 */
#ifndef HDC_PRECISION_HPP
#define HDC_PRECISION_HPP

namespace hdc {

// ---------------------------------------------------------------------------
// bits_for<V>::value -- the number of bits needed to represent 0..V inclusive.
//
// Implemented as a recursive template rather than a constexpr function so it
// works identically across every Vitis HLS version we target, and so it can be
// used in a template argument without relying on constexpr evaluation rules.
//
//   bits_for<0>  = 0     (no value to represent)
//   bits_for<1>  = 1     0..1
//   bits_for<6>  = 3     0..6   -> 110b
//   bits_for<8>  = 4     0..8   -> 1000b
//   bits_for<16> = 5     0..16  -> 10000b
//   bits_for<256>  = 9
//   bits_for<10240> = 14
// ---------------------------------------------------------------------------
template <unsigned long V>
struct bits_for {
    static const int value = 1 + bits_for<(V >> 1)>::value;
};
template <>
struct bits_for<0UL> {
    static const int value = 0;
};

// ---------------------------------------------------------------------------
// bundle_acc_bits<N> -- width of a bundle accumulator summing N hypervectors.
//
// bundle() adds one 0/1 element per input hypervector into a per-dimension
// accumulator, so the accumulator ranges over 0..N and is UNSIGNED. threshold()
// then compares it against N/2, which is inside that range.
//
// Exactly sufficient: one bit fewer and a dimension where every input was 1
// wraps to 0, flipping that bit of the query in the direction of maximum error.
// ---------------------------------------------------------------------------
template <unsigned long N>
struct bundle_acc_bits {
    static const int value = bits_for<N>::value;
};

// ---------------------------------------------------------------------------
// hamming_score_bits<D> -- width of a Hamming-distance accumulator over D dims.
//
// similarity_search accumulates (query[i] ^ proto[k][i]) across D dimensions,
// so the score ranges over 0..D. The accumulator is declared SIGNED (sim_t is
// used for dot-product families too, which go negative), hence the +1: D needs
// bits_for(D) magnitude bits plus a sign bit.
//
// This is the width the applications were getting wrong. At D=256 the rule
// gives 10 bits against the hardcoded 32; at D=10240 it gives 15.
// ---------------------------------------------------------------------------
template <unsigned long D>
struct hamming_score_bits {
    static const int value = bits_for<D>::value + 1;
};

// ---------------------------------------------------------------------------
// dot_score_bits<D, EBITS> -- width of a dot-product accumulator over D dims
// whose elements are EBITS-wide signed integers.
//
// Each product needs 2*EBITS bits; summing D of them adds bits_for(D). Not used
// by the binary applications, but stated here so the integer path has a rule to
// point at rather than another hardcoded constant.
// ---------------------------------------------------------------------------
template <unsigned long D, unsigned long EBITS>
struct dot_score_bits {
    static const int value = (int)(2 * EBITS) + bits_for<D>::value;
};

} // namespace hdc

#endif // HDC_PRECISION_HPP
