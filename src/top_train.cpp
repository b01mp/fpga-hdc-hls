/**
 * @file top_train.cpp
 * @brief Prototype-build + inference HDC composition.
 *
 * The top encodes a small labeled training set, builds class prototypes by
 * bundling encoded samples per class, thresholds the prototypes, then encodes a
 * query sample and searches the generated prototypes.
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "memory/gather.hpp"
#include "encoding/bind.hpp"
#include "aggregation/bundle.hpp"
#include "aggregation/threshold.hpp"
#include "search/similarity_search.hpp"

#ifndef TRAIN_D
#define TRAIN_D 128
#endif
#ifndef TRAIN_F
#define TRAIN_F 8
#endif
#ifndef TRAIN_L
#define TRAIN_L 8
#endif
#ifndef TRAIN_K
#define TRAIN_K 4
#endif
#ifndef TRAIN_N
#define TRAIN_N 8
#endif
#ifndef TRAIN_DP
#define TRAIN_DP 8
#endif
#ifndef TRAIN_CP
#define TRAIN_CP 2
#endif

typedef ap_uint<4> train_sample_acc_t;  // enough for TRAIN_F <= 15
typedef ap_uint<4> train_class_acc_t;   // enough for TRAIN_N <= 15
typedef ap_int<32> train_sim_t;

static void encode_record(
    const hdc::binary_t feature_codebook[TRAIN_F][TRAIN_D],
    const hdc::binary_t value_codebook[TRAIN_L][TRAIN_D],
    const ap_uint<3> value_indices[TRAIN_F],
    hdc::binary_t out[TRAIN_D]) {

    hdc::binary_t feature_hv[TRAIN_D];
    hdc::binary_t value_hv[TRAIN_D];
    hdc::binary_t bound_hv[TRAIN_D];
    train_sample_acc_t acc[TRAIN_D];

    #pragma HLS ARRAY_PARTITION variable=feature_hv cyclic factor=TRAIN_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=value_hv   cyclic factor=TRAIN_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=bound_hv   cyclic factor=TRAIN_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=acc        cyclic factor=TRAIN_DP dim=1

ENC_INIT:
    for (int d = 0; d < TRAIN_D; ++d) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=TRAIN_DP
        acc[d] = 0;
    }

ENC_FEATURES:
    for (int f = 0; f < TRAIN_F; ++f) {
        hdc::gather<hdc::binary_t, TRAIN_F, TRAIN_D, TRAIN_DP>(
            feature_codebook, f, feature_hv);

        const int level = (int)value_indices[f];
        hdc::gather<hdc::binary_t, TRAIN_L, TRAIN_D, TRAIN_DP>(
            value_codebook, level, value_hv);

        hdc::bind<hdc::binary_t, TRAIN_D, hdc::binary_tag, TRAIN_DP>(
            feature_hv, value_hv, bound_hv);

        hdc::bundle<hdc::binary_t, train_sample_acc_t, TRAIN_D, TRAIN_DP>(
            bound_hv, acc);
    }

    hdc::threshold<train_sample_acc_t, hdc::binary_t, TRAIN_D,
                   hdc::binary_tag, TRAIN_DP>(
        acc, out, TRAIN_F, hdc::TIE_SET_ZERO);
}

int train_infer_top(
    const hdc::binary_t feature_codebook[TRAIN_F][TRAIN_D],
    const hdc::binary_t value_codebook[TRAIN_L][TRAIN_D],
    const ap_uint<3> train_values[TRAIN_N][TRAIN_F],
    const ap_uint<2> train_labels[TRAIN_N],
    const ap_uint<3> query_values[TRAIN_F]) {

    train_class_acc_t proto_acc[TRAIN_K][TRAIN_D];
    hdc::binary_t prototypes[TRAIN_K][TRAIN_D];
    hdc::binary_t sample_hv[TRAIN_D];
    hdc::binary_t query_hv[TRAIN_D];
    ap_uint<4> class_counts[TRAIN_K];

    #pragma HLS ARRAY_PARTITION variable=proto_acc  cyclic factor=TRAIN_CP dim=1
    #pragma HLS ARRAY_PARTITION variable=proto_acc  cyclic factor=TRAIN_DP dim=2
    #pragma HLS ARRAY_PARTITION variable=prototypes cyclic factor=TRAIN_CP dim=1
    #pragma HLS ARRAY_PARTITION variable=prototypes cyclic factor=TRAIN_DP dim=2
    #pragma HLS ARRAY_PARTITION variable=sample_hv  cyclic factor=TRAIN_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=query_hv   cyclic factor=TRAIN_DP dim=1

INIT_CLASSES:
    for (int k = 0; k < TRAIN_K; ++k) {
        class_counts[k] = 0;
    INIT_PROTO_DIM:
        for (int d = 0; d < TRAIN_D; ++d) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL factor=TRAIN_DP
            proto_acc[k][d] = 0;
        }
    }

TRAIN_SAMPLES:
    for (int n = 0; n < TRAIN_N; ++n) {
        encode_record(feature_codebook, value_codebook, train_values[n],
                      sample_hv);

        const int label = (int)train_labels[n];
        class_counts[label]++;

    ADD_SAMPLE:
        for (int d = 0; d < TRAIN_D; ++d) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL factor=TRAIN_DP
            proto_acc[label][d] += (train_class_acc_t)sample_hv[d];
        }
    }

MAKE_PROTOTYPES:
    for (int k = 0; k < TRAIN_K; ++k) {
        hdc::threshold<train_class_acc_t, hdc::binary_t, TRAIN_D,
                       hdc::binary_tag, TRAIN_DP>(
            proto_acc[k], prototypes[k], (int)class_counts[k],
            hdc::TIE_SET_ZERO);
    }

    encode_record(feature_codebook, value_codebook, query_values, query_hv);

    return hdc::similarity_search<hdc::binary_t, train_sim_t, TRAIN_D, TRAIN_K,
                                  hdc::binary_tag, TRAIN_DP, TRAIN_CP>(
        query_hv, prototypes, hdc::SIM_HAMMING, hdc::SEARCH_ARGMIN);
}
