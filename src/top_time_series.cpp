/**
 * @file top_time_series.cpp
 * @brief Paper application: time-series classification composition.
 *
 * Data path for one quantized temporal window:
 *
 *   gather(sample-level) -> permute(position) -> bundle  (repeat TS_W times)
 *                         -> threshold -> similarity_search -> class
 *
 * PER-STAGE PRECISION -- see common/hdc_precision.hpp for the rules.
 *
 *   ts_acc_t   bundle accumulator, holds 0..TS_W   -> bits_for(TS_W)
 *   ts_sim_t   Hamming score,      holds 0..TS_D   -> bits_for(TS_D) + 1
 *
 * NOTE: this is the application where the derived rule DISAGREES with the
 * previous hand-written constant. TS_W = 6 needs 3 bits (0..6 is 110b); the
 * file previously declared ap_uint<4> with the comment "enough for TS_W <= 15".
 * That was safe but a bit generous -- it was sized for a bound on TS_W rather
 * than for TS_W itself. Deriving the width removes that kind of drift, which is
 * exactly the failure mode a hand-computed constant invites when the parameter
 * later changes.
 *
 * Override with -DTS_ACC_BITS / -DTS_SIM_BITS for the precision sweep.
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "common/hdc_precision.hpp"
#include "application/shared_composition.hpp"

#ifndef TS_D
#define TS_D 1024
#endif
#ifndef TS_W
#define TS_W 6
#endif
#ifndef TS_V
#define TS_V 12
#endif
#ifndef TS_K
#define TS_K 64
#endif
#ifndef TS_DP
#define TS_DP 8
#endif
#ifndef TS_CP
#define TS_CP 2
#endif

// ---- per-stage intermediate widths ----------------------------------------
#ifndef TS_ACC_BITS
#define TS_ACC_BITS (hdc::bundle_acc_bits<TS_W>::value)
#endif
#ifndef TS_SIM_BITS
#define TS_SIM_BITS (hdc::hamming_score_bits<TS_D>::value)
#endif

typedef ap_uint<TS_ACC_BITS> ts_acc_t;  // bundle accumulator, 0..TS_W
typedef ap_int <TS_SIM_BITS> ts_sim_t;  // Hamming-distance accumulator, 0..TS_D

int time_series_classification_top(
    const hdc::binary_t sample_codebook[TS_V][TS_D],
    const ap_uint<4> window_indices[TS_W],
    const hdc::binary_t prototypes[TS_K][TS_D]) {

    hdc::binary_t query_hv[TS_D];
    #pragma HLS ARRAY_PARTITION variable=query_hv cyclic factor=TS_DP dim=1

    hdc_app::encode_ordered_window_query<TS_D, TS_W, TS_V, TS_DP, ts_acc_t>(
        sample_codebook, window_indices, query_hv);

    return hdc_app::search_binary_references<TS_D, TS_K, TS_DP, TS_CP,
                                             ts_sim_t>(
        query_hv, prototypes);
}
