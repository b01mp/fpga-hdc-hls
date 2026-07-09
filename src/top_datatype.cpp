/**
 * @file top_datatype.cpp
 * @brief Datatype-sweep synthesis tops (Novelty 1 demonstration).
 *
 * Nine concrete tops = 3 datatype-specialized primitives (bind, threshold,
 * similarity_search) x 3 datatype families (binary, bipolar, fixed). EVERYTHING
 * is held constant (D=256, DP=8, CP=2, part, clock) so the ONLY variable across a
 * primitive's three tops is the datatype -- any difference in the csynth report is
 * purely the datatype's effect. Expected: binary/bipolar use LUTs (XOR / sign-mul),
 * fixed uses DSPs (real multiply).
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
typedef ap_int<32>       iacc_t;    // integer accumulator (binary/bipolar)
typedef ap_fixed<32, 16> facc_t;    // fixed-point accumulator
typedef ap_int<32>       isim_t;    // integer similarity score
typedef ap_fixed<32, 16> fsim_t;    // fixed-point similarity score

// ---- bind : XOR (binary) vs sign-multiply (bipolar) vs multiply (fixed) ----
void bind_binary_top(const hdc::binary_t a[DT_D], const hdc::binary_t b[DT_D], hdc::binary_t out[DT_D]) {
    hdc::bind<hdc::binary_t, DT_D, hdc::binary_tag, DT_DP>(a, b, out);
}
void bind_bipolar_top(const hdc::bipolar_t a[DT_D], const hdc::bipolar_t b[DT_D], hdc::bipolar_t out[DT_D]) {
    hdc::bind<hdc::bipolar_t, DT_D, hdc::bipolar_tag, DT_DP>(a, b, out);
}
void bind_fixed_top(const fx_t a[DT_D], const fx_t b[DT_D], fx_t out[DT_D]) {
    hdc::bind<fx_t, DT_D, hdc::fixed_tag, DT_DP>(a, b, out);
}

// ---- threshold : majority (binary) vs sign (bipolar) vs passthrough (fixed) ----
void threshold_binary_top(const iacc_t acc[DT_D], hdc::binary_t out[DT_D], int count) {
    hdc::threshold<iacc_t, hdc::binary_t, DT_D, hdc::binary_tag, DT_DP>(acc, out, count);
}
void threshold_bipolar_top(const iacc_t acc[DT_D], hdc::bipolar_t out[DT_D], int count) {
    hdc::threshold<iacc_t, hdc::bipolar_t, DT_D, hdc::bipolar_tag, DT_DP>(acc, out, count);
}
void threshold_fixed_top(const facc_t acc[DT_D], fx_t out[DT_D], int count) {
    hdc::threshold<facc_t, fx_t, DT_D, hdc::fixed_tag, DT_DP>(acc, out, count);
}

// ---- similarity_search : Hamming (binary) vs dot-product (bipolar/fixed) ----
int sim_binary_top(const hdc::binary_t q[DT_D], const hdc::binary_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<hdc::binary_t, isim_t, DT_D, DT_K, hdc::binary_tag, DT_DP, DT_CP>(q, proto);
}
int sim_bipolar_top(const hdc::bipolar_t q[DT_D], const hdc::bipolar_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<hdc::bipolar_t, isim_t, DT_D, DT_K, hdc::bipolar_tag, DT_DP, DT_CP>(q, proto);
}
int sim_fixed_top(const fx_t q[DT_D], const fx_t proto[DT_K][DT_D]) {
    return hdc::similarity_search<fx_t, fsim_t, DT_D, DT_K, hdc::fixed_tag, DT_DP, DT_CP>(q, proto);
}
