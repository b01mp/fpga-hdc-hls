/**
 * @file top_datatype.cpp
 * @brief Datatype-sweep synthesis tops (Novelty 1 demonstration).
 *
 * Fifteen concrete tops = 3 datatype-specialized primitives (bind, threshold,
 * similarity_search) x 5 datatype families (binary, bipolar, fixed, integer,
 * pow2). D, DP, CP, part and clock are held constant, so the ONLY variable
 * across a primitive's tops is the datatype -- any difference in the csynth
 * report is purely the datatype's effect.
 *
 * Expected:
 *   binary  -- XOR / majority / Hamming         -> LUTs only
 *   bipolar -- sign-multiply / sign / dot       -> LUTs, few DSPs
 *   fixed   -- real multiply / passthru / dot   -> DSPs + alignment logic
 *   integer -- real multiply / passthru / dot   -> DSPs, no alignment logic
 *              (this is the family behind BIO_X=32, i.e. the BioHD result)
 *   pow2    -- sign XOR + exponent ADD, shift   -> LUTs only, NO DSPs, and a
 *              6-bit element instead of 32 at the same dynamic range
 *
 * ON ACCUMULATOR / SCORE WIDTHS. These are NOT held constant, and should not be:
 * the width needed is *determined by* the element datatype. A binary score needs
 * ~log2(D) bits; an int32 dot product needs 32+32+log2(D). Forcing one width on
 * all families would make binary wasteful and int32 numerically wrong. The width
 * is part of the datatype's cost, not a confound. pow2 deliberately reuses the
 * binary/bipolar widths because its DECODED values live in the same range.
 *
 * ON INTEGER vs FIXED. Both synthesize the same core multiplier, but ap_fixed
 * adds binary-point alignment, rounding and saturation logic on top -- so fixed
 * is never cheaper than integer at equal width. An HDC prototype is a bundled
 * COUNT, which is integral, so integer is also the semantically correct choice.
 *
 * ON THE TWO INTEGER COST POINTS. sim_integer_top below is a full multiply
 * (both operands are elem_t). The off-chip streaming path in
 * similarity_search_stream_dt.hpp is cheaper for the same family because the
 * QUERY is always binary there, reducing the dot product to a conditional
 * add/subtract with no multiplier. Quote the two numbers separately.
 */
#include <ap_int.h>
#include <ap_fixed.h>
#include "common/hdc_types.hpp"
#include "encoding/bind.hpp"
#include "aggregation/threshold.hpp"
#include "search/similarity_search.hpp"

#define DT_D  256    // hv_dim
#define DT_K  10     // num_prototypes (search)
#define DT_DP 8      // dimension_parallelism (held constant)
#define DT_CP 2      // class_parallelism (search, held constant)

typedef ap_fixed<16, 8>  fx_t;      // fixed-point element
typedef ap_int<32>       int_t;     // int32 element (BioHD high-precision library)
typedef ap_int<32>       iacc_t;    // accumulator: binary / bipolar / pow2
typedef ap_fixed<32, 16> facc_t;    // accumulator: fixed-point
typedef ap_int<48>       i32acc_t;  // accumulator: int32 elements summed over D
typedef ap_int<32>       isim_t;    // score: binary / bipolar / pow2
typedef ap_fixed<32, 16> fsim_t;    // score: fixed-point
typedef ap_int<64>       i32sim_t;  // score: 32x32 products summed over D

// ---- bind : XOR (binary) | sign-multiply (bipolar) | multiply (fixed,
//             integer) | sign-XOR + exponent-ADD (pow2) ----
void bind_binary_top(const hdc::binary_t a[DT_D], const hdc::binary_t b[DT_D], hdc::binary_t out[DT_D]) {
    hdc::bind<hdc::binary_t, DT_D, hdc::binary_tag, DT_DP>(a, b, out);
}
void bind_bipolar_top(const hdc::bipolar_t a[DT_D], const hdc::bipolar_t b[DT_D], hdc::bipolar_t out[DT_D]) {
    hdc::bind<hdc::bipolar_t, DT_D, hdc::bipolar_tag, DT_DP>(a, b, out);
}
void bind_fixed_top(const fx_t a[DT_D], const fx_t b[DT_D], fx_t out[DT_D]) {
    hdc::bind<fx_t, DT_D, hdc::fixed_tag, DT_DP>(a, b, out);
}
void bind_integer_top(const int_t a[DT_D], const int_t b[DT_D], int_t out[DT_D]) {
    hdc::bind<int_t, DT_D, hdc::integer_tag, DT_DP>(a, b, out);
}
void bind_pow2_top(const hdc::pow2_t a[DT_D], const hdc::pow2_t b[DT_D], hdc::pow2_t out[DT_D]) {
    hdc::bind<hdc::pow2_t, DT_D, hdc::pow2_tag, DT_DP>(a, b, out);
}

// ---- threshold : majority (binary) | sign (bipolar) | passthrough (fixed,
//                  integer) | round-to-nearest-power-of-two (pow2) ----
void threshold_binary_top(const iacc_t acc[DT_D], hdc::binary_t out[DT_D], int count) {
    hdc::threshold<iacc_t, hdc::binary_t, DT_D, hdc::binary_tag, DT_DP>(acc, out, count);
}
void threshold_bipolar_top(const iacc_t acc[DT_D], hdc::bipolar_t out[DT_D], int count) {
    hdc::threshold<iacc_t, hdc::bipolar_t, DT_D, hdc::bipolar_tag, DT_DP>(acc, out, count);
}
void threshold_fixed_top(const facc_t acc[DT_D], fx_t out[DT_D], int count) {
    hdc::threshold<facc_t, fx_t, DT_D, hdc::fixed_tag, DT_DP>(acc, out, count);
}
void threshold_integer_top(const i32acc_t acc[DT_D], int_t out[DT_D], int count) {
    hdc::threshold<i32acc_t, int_t, DT_D, hdc::integer_tag, DT_DP>(acc, out, count);
}
void threshold_pow2_top(const iacc_t acc[DT_D], hdc::pow2_t out[DT_D], int count) {
    hdc::threshold<iacc_t, hdc::pow2_t, DT_D, hdc::pow2_tag, DT_DP>(acc, out, count);
}

// ---- similarity_search : Hamming (binary) | dot-product (bipolar, fixed,
//                          integer) | shift-and-accumulate dot (pow2) ----
int sim_binary_top(const hdc::binary_t q[DT_D], const hdc::binary_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<hdc::binary_t, isim_t, DT_D, DT_K, hdc::binary_tag, DT_DP, DT_CP>(q, proto);
}
int sim_bipolar_top(const hdc::bipolar_t q[DT_D], const hdc::bipolar_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<hdc::bipolar_t, isim_t, DT_D, DT_K, hdc::bipolar_tag, DT_DP, DT_CP>(q, proto);
}
int sim_fixed_top(const fx_t q[DT_D], const fx_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<fx_t, fsim_t, DT_D, DT_K, hdc::fixed_tag, DT_DP, DT_CP>(q, proto);
}
int sim_integer_top(const int_t q[DT_D], const int_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<int_t, i32sim_t, DT_D, DT_K, hdc::integer_tag, DT_DP, DT_CP>(q, proto);
}
int sim_pow2_top(const hdc::pow2_t q[DT_D], const hdc::pow2_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<hdc::pow2_t, isim_t, DT_D, DT_K, hdc::pow2_tag, DT_DP, DT_CP>(q, proto);
}
