/**
 * @file tb_application.cpp
 * @brief C-simulation testbench for image_classification_top.
 *
 * The expected result is computed with an independent scalar software path;
 * the reference deliberately does not call any HDC library primitive.
 */

#include <cstdio>
#include <ap_int.h>

#include "common/hdc_types.hpp"

#define APP_D  256
#define APP_F  16
#define APP_L  8
#define APP_K  10

int image_classification_top(
    const hdc::binary_t feature_codebook[APP_F][APP_D],
    const hdc::binary_t value_codebook[APP_L][APP_D],
    const ap_uint<3> value_indices[APP_F],
    const hdc::binary_t prototypes[APP_K][APP_D]);

static int software_reference(
    const hdc::binary_t feature_codebook[APP_F][APP_D],
    const hdc::binary_t value_codebook[APP_L][APP_D],
    const ap_uint<3> value_indices[APP_F],
    const hdc::binary_t prototypes[APP_K][APP_D],
    hdc::binary_t query_out[APP_D]) {

    // Scalar gather + XOR bind + bundle + majority threshold.
    for (int d = 0; d < APP_D; ++d) {
        int ones = 0;
        for (int f = 0; f < APP_F; ++f) {
            const int level = (int)value_indices[f];
            const int feature_bit = (int)feature_codebook[f][d];
            const int value_bit = (int)value_codebook[level][d];
            ones += feature_bit ^ value_bit;
        }

        // Matches TIE_SET_ZERO: exactly APP_F/2 ones resolves to zero.
        query_out[d] = (ones * 2 > APP_F) ? 1 : 0;
    }

    // Scalar Hamming-distance search with the same first-class tie policy.
    int best_class = 0;
    int best_distance = APP_D + 1;
    for (int c = 0; c < APP_K; ++c) {
        int distance = 0;
        for (int d = 0; d < APP_D; ++d) {
            distance += (int)query_out[d] ^ (int)prototypes[c][d];
        }
        if (distance < best_distance) {
            best_distance = distance;
            best_class = c;
        }
    }
    return best_class;
}

int main() {
    static hdc::binary_t feature_codebook[APP_F][APP_D];
    static hdc::binary_t value_codebook[APP_L][APP_D];
    static ap_uint<3> value_indices[APP_F];
    static hdc::binary_t prototypes[APP_K][APP_D];
    static hdc::binary_t reference_query[APP_D];

    // Deterministic codebooks exercise different feature, level, and dimension
    // combinations while keeping the test reproducible.
    for (int f = 0; f < APP_F; ++f) {
        value_indices[f] = (ap_uint<3>)((3 * f + 1) % APP_L);
        for (int d = 0; d < APP_D; ++d) {
            feature_codebook[f][d] =
                (hdc::binary_t)(((f * 13 + d * 7 + (d >> 2)) >> 1) & 1);
        }
    }

    for (int l = 0; l < APP_L; ++l) {
        for (int d = 0; d < APP_D; ++d) {
            value_codebook[l][d] =
                (hdc::binary_t)(((l * 11 + d * 5 + (d >> 3)) >> 2) & 1);
        }
    }

    // Compute the query first without relying on prototypes. A temporary
    // all-zero prototype table is sufficient because only query_out is needed.
    for (int c = 0; c < APP_K; ++c) {
        for (int d = 0; d < APP_D; ++d) {
            prototypes[c][d] = 0;
        }
    }
    software_reference(feature_codebook, value_codebook, value_indices,
                       prototypes, reference_query);

    // Every class starts as the complement of the query. Class 3 is then made
    // an exact match, so the expected winner is unique with Hamming distance 0.
    const int injected_class = 3;
    for (int c = 0; c < APP_K; ++c) {
        for (int d = 0; d < APP_D; ++d) {
            prototypes[c][d] = (hdc::binary_t)(1 ^ (int)reference_query[d]);
        }
    }
    for (int d = 0; d < APP_D; ++d) {
        prototypes[injected_class][d] = reference_query[d];
    }

    const int expected = software_reference(
        feature_codebook, value_codebook, value_indices,
        prototypes, reference_query);
    const int actual = image_classification_top(
        feature_codebook, value_codebook, value_indices, prototypes);

    std::printf("Expected label: %d\n", expected);
    std::printf("Actual label:   %d\n", actual);

    if (expected != injected_class) {
        std::printf("FAIL: reference setup expected injected class %d\n",
                    injected_class);
        return 1;
    }
    if (actual != expected) {
        std::printf("FAIL: composed top disagrees with software reference\n");
        return 1;
    }

    std::printf("== tb_application: ALL PASS ==\n");
    return 0;
}
