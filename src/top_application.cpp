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
#include "application/shared_composition.hpp"

// First application-level DSE candidate. Defaults stay concrete so Vitis HLS has
// a fixed synthesis top, while TCL scripts may override parallelism with -D.
#ifndef APP_D
#define APP_D  256  // hypervector dimension
#endif
#ifndef APP_F
#define APP_F  16   // number of input features / position hypervectors
#endif
#ifndef APP_L
#define APP_L  8    // number of quantized value levels
#endif
#ifndef APP_K
#define APP_K  10   // number of class prototypes
#endif
#ifndef APP_DP
#define APP_DP 8    // dimension parallelism
#endif
#ifndef APP_CP
#define APP_CP 2    // class parallelism in similarity search
#endif

typedef ap_uint<5>  app_acc_t;  // ceil(log2(APP_F + 1)); represents 0..16
typedef ap_int<32>  app_sim_t;  // Hamming-distance accumulator

int image_classification_top(
    const hdc::binary_t feature_codebook[APP_F][APP_D],
    const hdc::binary_t value_codebook[APP_L][APP_D],
    const ap_uint<3> value_indices[APP_F],
    const hdc::binary_t prototypes[APP_K][APP_D]) {

    hdc::binary_t query_hv[APP_D];

    #pragma HLS ARRAY_PARTITION variable=query_hv   cyclic factor=APP_DP dim=1

    hdc_app::encode_feature_value_query<APP_D, APP_F, APP_L, APP_DP,
                                        app_acc_t>(
        feature_codebook, value_codebook, value_indices, query_hv);

    // Binary similarity_search computes Hamming distance and returns argmin.
    return hdc_app::search_binary_references<APP_D, APP_K, APP_DP, APP_CP,
                                             app_sim_t>(
        query_hv, prototypes);
}
