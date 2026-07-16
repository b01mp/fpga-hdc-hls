/**
 * @file shared_composition.hpp
 * @brief Shared HDC application compositions used by the paper case studies.
 */
#ifndef HDC_APPLICATION_SHARED_COMPOSITION_HPP
#define HDC_APPLICATION_SHARED_COMPOSITION_HPP

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "memory/gather.hpp"
#include "encoding/bind.hpp"
#include "encoding/permute.hpp"
#include "aggregation/bundle.hpp"
#include "aggregation/threshold.hpp"
#include "search/similarity_search.hpp"

namespace hdc_app {

template <int D, int F, int L, int DP, typename acc_t>
void encode_feature_value_query(
    const hdc::binary_t feature_codebook[F][D],
    const hdc::binary_t value_codebook[L][D],
    const ap_uint<3> value_indices[F],
    hdc::binary_t query[D]) {

    hdc::binary_t feature_hv[D];
    hdc::binary_t value_hv[D];
    hdc::binary_t bound_hv[D];
    acc_t acc[D];

    #pragma HLS ARRAY_PARTITION variable=feature_hv cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=value_hv   cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=bound_hv   cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=acc        cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=query      cyclic factor=DP dim=1

INIT_FEATURE_VALUE_ACC:
    for (int d = 0; d < D; ++d) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=DP
        acc[d] = 0;
    }

FEATURE_VALUE_LOOP:
    for (int f = 0; f < F; ++f) {
        hdc::gather<hdc::binary_t, F, D, DP>(feature_codebook, f, feature_hv);

        const int level = (int)value_indices[f];
        hdc::gather<hdc::binary_t, L, D, DP>(value_codebook, level, value_hv);

        hdc::bind<hdc::binary_t, D, hdc::binary_tag, DP>(
            feature_hv, value_hv, bound_hv);

        hdc::bundle<hdc::binary_t, acc_t, D, DP>(bound_hv, acc);
    }

    hdc::threshold<acc_t, hdc::binary_t, D, hdc::binary_tag, DP>(
        acc, query, F, hdc::TIE_SET_ZERO);
}

template <int D, int W, int V, int DP, typename acc_t>
void encode_ordered_window_query(
    const hdc::binary_t symbol_codebook[V][D],
    const ap_uint<4> symbol_indices[W],
    hdc::binary_t query[D]) {

    hdc::binary_t symbol_hv[D];
    hdc::binary_t positional_hv[D];
    acc_t acc[D];

    #pragma HLS ARRAY_PARTITION variable=symbol_hv     cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=positional_hv cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=acc           cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=query         cyclic factor=DP dim=1

INIT_ORDERED_ACC:
    for (int d = 0; d < D; ++d) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=DP
        acc[d] = 0;
    }

ORDERED_WINDOW_LOOP:
    for (int w = 0; w < W; ++w) {
        const int symbol = (int)symbol_indices[w];
        hdc::gather<hdc::binary_t, V, D, DP>(
            symbol_codebook, symbol, symbol_hv);

        hdc::permute<hdc::binary_t, D, DP>(symbol_hv, w, positional_hv);

        hdc::bundle<hdc::binary_t, acc_t, D, DP>(positional_hv, acc);
    }

    hdc::threshold<acc_t, hdc::binary_t, D, hdc::binary_tag, DP>(
        acc, query, W, hdc::TIE_SET_ZERO);
}

template <int D, int K, int DP, int CP, typename sim_t>
int search_binary_references(
    const hdc::binary_t query[D],
    const hdc::binary_t references[K][D]) {

    return hdc::similarity_search<hdc::binary_t, sim_t, D, K,
                                  hdc::binary_tag, DP, CP>(
        query, references, hdc::SIM_HAMMING, hdc::SEARCH_ARGMIN);
}

} // namespace hdc_app

#endif // HDC_APPLICATION_SHARED_COMPOSITION_HPP
