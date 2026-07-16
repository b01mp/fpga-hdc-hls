/**
 * @file top_time_series.cpp
 * @brief Paper application: time-series classification composition.
 *
 * Data path for one quantized temporal window:
 *
 *   gather(sample-level) -> permute(position) -> bundle  (repeat TS_W times)
 *                         -> threshold -> similarity_search -> class
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "application/shared_composition.hpp"

#ifndef TS_D
#define TS_D 128
#endif
#ifndef TS_W
#define TS_W 6
#endif
#ifndef TS_V
#define TS_V 12
#endif
#ifndef TS_K
#define TS_K 4
#endif
#ifndef TS_DP
#define TS_DP 8
#endif
#ifndef TS_CP
#define TS_CP 2
#endif

typedef ap_uint<4> ts_acc_t;  // enough for TS_W <= 15
typedef ap_int<32> ts_sim_t;

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
