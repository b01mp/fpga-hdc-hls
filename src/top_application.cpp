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
 *
 * PER-STAGE PRECISION. The two intermediates are sized by DIFFERENT rules,
 * both in common/hdc_precision.hpp:
 *
 *   app_acc_t   bundle accumulator, holds 0..APP_F      -> bits_for(APP_F)
 *   app_sim_t   Hamming score,      holds 0..APP_D      -> bits_for(APP_D) + 1
 *
 * At the defaults below that is 5 bits and 12 bits. They do not move together:
 * APP_F is a property of the input, APP_D of the hypervector space. A single
 * global precision setting cannot serve both -- wide enough for the score and
 * the accumulator wastes 7 bits per dimension; narrow enough for the
 * accumulator and the score wraps.
 *
 * Override either with -DAPP_ACC_BITS / -DAPP_SIM_BITS. The precision sweep
 * uses that to synthesize the over-provisioned, right-sized, and deliberately
 * under-sized configurations of the same design.
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "common/hdc_precision.hpp"
#include "application/shared_composition.hpp"

// First application-level DSE candidate. Defaults stay concrete so Vitis HLS has
// a fixed synthesis top, while TCL scripts may override parallelism with -D.
#ifndef APP_D
#define APP_D  1024 // hypervector dimension
#endif
#ifndef APP_F
#define APP_F  16   // number of input features / position hypervectors
#endif
#ifndef APP_L
#define APP_L  8    // number of quantized value levels
#endif
#ifndef APP_K
#define APP_K  64   // number of class prototypes
#endif
#ifndef APP_DP
#define APP_DP 8    // dimension parallelism
#endif
#ifndef APP_CP
#define APP_CP 2    // class parallelism in similarity search
#endif

// ---- per-stage intermediate widths ----------------------------------------
// Derived, not hand-computed, so they follow APP_F and APP_D automatically.
#ifndef APP_ACC_BITS
#define APP_ACC_BITS (hdc::bundle_acc_bits<APP_F>::value)
#endif
#ifndef APP_SIM_BITS
#define APP_SIM_BITS (hdc::hamming_score_bits<APP_D>::value)
#endif

typedef ap_uint<APP_ACC_BITS> app_acc_t;  // bundle accumulator, 0..APP_F
typedef ap_int <APP_SIM_BITS> app_sim_t;  // Hamming-distance accumulator, 0..APP_D

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
