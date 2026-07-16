/**
 * @file tb_train.cpp
 * @brief C-simulation testbench for train_infer_top.
 */

#include <cstdio>
#include <ap_int.h>

#include "common/hdc_types.hpp"

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

int train_infer_top(
    const hdc::binary_t feature_codebook[TRAIN_F][TRAIN_D],
    const hdc::binary_t value_codebook[TRAIN_L][TRAIN_D],
    const ap_uint<3> train_values[TRAIN_N][TRAIN_F],
    const ap_uint<2> train_labels[TRAIN_N],
    const ap_uint<3> query_values[TRAIN_F]);

static void encode_record_ref(
    const hdc::binary_t feature_codebook[TRAIN_F][TRAIN_D],
    const hdc::binary_t value_codebook[TRAIN_L][TRAIN_D],
    const ap_uint<3> values[TRAIN_F],
    hdc::binary_t out[TRAIN_D]) {

    for (int d = 0; d < TRAIN_D; ++d) {
        int ones = 0;
        for (int f = 0; f < TRAIN_F; ++f) {
            const int level = (int)values[f];
            ones += (int)feature_codebook[f][d] ^
                    (int)value_codebook[level][d];
        }
        out[d] = (ones * 2 > TRAIN_F) ? 1 : 0;
    }
}

static int software_reference(
    const hdc::binary_t feature_codebook[TRAIN_F][TRAIN_D],
    const hdc::binary_t value_codebook[TRAIN_L][TRAIN_D],
    const ap_uint<3> train_values[TRAIN_N][TRAIN_F],
    const ap_uint<2> train_labels[TRAIN_N],
    const ap_uint<3> query_values[TRAIN_F]) {

    int proto_acc[TRAIN_K][TRAIN_D];
    int class_counts[TRAIN_K];
    hdc::binary_t sample_hv[TRAIN_D];
    hdc::binary_t prototypes[TRAIN_K][TRAIN_D];
    hdc::binary_t query_hv[TRAIN_D];

    for (int k = 0; k < TRAIN_K; ++k) {
        class_counts[k] = 0;
        for (int d = 0; d < TRAIN_D; ++d) {
            proto_acc[k][d] = 0;
        }
    }

    for (int n = 0; n < TRAIN_N; ++n) {
        encode_record_ref(feature_codebook, value_codebook,
                          train_values[n], sample_hv);
        const int label = (int)train_labels[n];
        class_counts[label]++;
        for (int d = 0; d < TRAIN_D; ++d) {
            proto_acc[label][d] += (int)sample_hv[d];
        }
    }

    for (int k = 0; k < TRAIN_K; ++k) {
        for (int d = 0; d < TRAIN_D; ++d) {
            prototypes[k][d] =
                (proto_acc[k][d] * 2 > class_counts[k]) ? 1 : 0;
        }
    }

    encode_record_ref(feature_codebook, value_codebook,
                      query_values, query_hv);

    int best_class = 0;
    int best_distance = TRAIN_D + 1;
    for (int k = 0; k < TRAIN_K; ++k) {
        int distance = 0;
        for (int d = 0; d < TRAIN_D; ++d) {
            distance += (int)query_hv[d] ^ (int)prototypes[k][d];
        }
        if (distance < best_distance) {
            best_distance = distance;
            best_class = k;
        }
    }
    return best_class;
}

int main() {
    static hdc::binary_t feature_codebook[TRAIN_F][TRAIN_D];
    static hdc::binary_t value_codebook[TRAIN_L][TRAIN_D];
    static ap_uint<3> train_values[TRAIN_N][TRAIN_F];
    static ap_uint<2> train_labels[TRAIN_N];
    static ap_uint<3> query_values[TRAIN_F];

    for (int f = 0; f < TRAIN_F; ++f) {
        for (int d = 0; d < TRAIN_D; ++d) {
            feature_codebook[f][d] =
                (hdc::binary_t)(((f * 11 + d * 7 + (d >> 2)) >> 1) & 1);
        }
    }
    for (int l = 0; l < TRAIN_L; ++l) {
        for (int d = 0; d < TRAIN_D; ++d) {
            value_codebook[l][d] =
                (hdc::binary_t)(((l * 13 + d * 3 + (d >> 3)) >> 2) & 1);
        }
    }

    for (int n = 0; n < TRAIN_N; ++n) {
        train_labels[n] = (ap_uint<2>)(n % TRAIN_K);
        for (int f = 0; f < TRAIN_F; ++f) {
            train_values[n][f] = (ap_uint<3>)((n + 2 * f + 1) % TRAIN_L);
        }
    }

    const int query_source = 6;
    for (int f = 0; f < TRAIN_F; ++f) {
        query_values[f] = train_values[query_source][f];
    }

    const int expected = software_reference(
        feature_codebook, value_codebook, train_values, train_labels,
        query_values);
    const int actual = train_infer_top(
        feature_codebook, value_codebook, train_values, train_labels,
        query_values);

    std::printf("Expected label: %d\n", expected);
    std::printf("Actual label:   %d\n", actual);

    if (actual != expected) {
        std::printf("FAIL: train/infer top disagrees with software reference\n");
        return 1;
    }

    std::printf("== tb_train: ALL PASS ==\n");
    return 0;
}
