/**
 * @file top_application.cpp
 * @brief Non-streamed image-classification composition of the HDC primitives.
 *
 * Data path for one input sample:
 *
 *   gather(position) -> gather(level) -> bind -> bundle  (repeat APP_F times)
 *                    -> threshold -> similarity_search -> predicted class
 *
 * The intermediate hypervectors are deliberately materialized in local arrays.
 * This is the first, staged application-level validation top; it does not overlap
 * different samples with DATAFLOW or streaming FIFOs.
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "memory/gather.hpp"
#include "encoding/bind.hpp"
#include "aggregation/bundle.hpp"
#include "aggregation/threshold.hpp"
#include "search/similarity_search.hpp"

// First application-level DSE candidate. Keep these concrete so Vitis HLS has a
// fixed synthesis top; later candidates can change the constants or use wrappers.
#define APP_D  256  // hypervector dimension
#define APP_F  16   // number of input features / position hypervectors
#define APP_L  8    // number of quantized value levels
#define APP_K  10   // number of class prototypes
#define APP_DP 8    // dimension parallelism
#define APP_CP 2    // class parallelism in similarity search

typedef ap_uint<5>  app_acc_t;  // ceil(log2(APP_F + 1)); represents 0..16
typedef ap_int<32>  app_sim_t;  // Hamming-distance accumulator

int image_classification_top(
    const hdc::binary_t feature_codebook[APP_F][APP_D],
    const hdc::binary_t value_codebook[APP_L][APP_D],
    const ap_uint<3> value_indices[APP_F],
    const hdc::binary_t prototypes[APP_K][APP_D]) {

    // Stage boundaries. Reused for each feature because execution is staged,
    // rather than overlapped across features or input samples.
    hdc::binary_t feature_hv[APP_D];
    hdc::binary_t value_hv[APP_D];
    hdc::binary_t bound_hv[APP_D];
    app_acc_t      acc[APP_D];
    hdc::binary_t query_hv[APP_D];

    #pragma HLS ARRAY_PARTITION variable=feature_hv cyclic factor=APP_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=value_hv   cyclic factor=APP_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=bound_hv   cyclic factor=APP_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=acc        cyclic factor=APP_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=query_hv   cyclic factor=APP_DP dim=1

    // bundle() performs acc += in, so each sample must start from zero.
INIT_ACC:
    for (int d = 0; d < APP_D; ++d) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=APP_DP
        acc[d] = 0;
    }

FEATURE_LOOP:
    for (int f = 0; f < APP_F; ++f) {
        // Position/feature codebook row f.
        hdc::gather<hdc::binary_t, APP_F, APP_D, APP_DP>(
            feature_codebook, f, feature_hv);

        // Quantized value selects one level-codebook row.
        const int level = (int)value_indices[f];
        hdc::gather<hdc::binary_t, APP_L, APP_D, APP_DP>(
            value_codebook, level, value_hv);

        // Binary binding is XOR, producing one encoded feature HV.
        hdc::bind<hdc::binary_t, APP_D, hdc::binary_tag, APP_DP>(
            feature_hv, value_hv, bound_hv);

        // Accumulate all encoded feature HVs dimension by dimension.
        hdc::bundle<hdc::binary_t, app_acc_t, APP_D, APP_DP>(
            bound_hv, acc);
    }

    // Majority vote over the APP_F encoded features produces the query HV.
    hdc::threshold<app_acc_t, hdc::binary_t, APP_D,
                   hdc::binary_tag, APP_DP>(
        acc, query_hv, APP_F, hdc::TIE_SET_ZERO);

    // Binary similarity_search computes Hamming distance and returns argmin.
    return hdc::similarity_search<hdc::binary_t, app_sim_t, APP_D, APP_K,
                                  hdc::binary_tag, APP_DP, APP_CP>(
        query_hv, prototypes, hdc::SIM_HAMMING, hdc::SEARCH_ARGMIN);
}
