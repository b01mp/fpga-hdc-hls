/**
 * @file tb_time_series.cpp
 * @brief C-simulation testbench for time_series_classification_top.
 */

#include <cstdio>
#include <ap_int.h>

#include "common/hdc_types.hpp"

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

int time_series_classification_top(
    const hdc::binary_t sample_codebook[TS_V][TS_D],
    const ap_uint<4> window_indices[TS_W],
    const hdc::binary_t prototypes[TS_K][TS_D]);

static void encode_window_ref(
    const hdc::binary_t sample_codebook[TS_V][TS_D],
    const ap_uint<4> window_indices[TS_W],
    hdc::binary_t query[TS_D]) {

    for (int d = 0; d < TS_D; ++d) {
        int ones = 0;
        for (int t = 0; t < TS_W; ++t) {
            const int token = (int)window_indices[t];
            const int source = (d - t + TS_D) % TS_D;
            ones += (int)sample_codebook[token][source];
        }
        query[d] = (ones * 2 > TS_W) ? 1 : 0;
    }
}

static int search_ref(
    const hdc::binary_t query[TS_D],
    const hdc::binary_t prototypes[TS_K][TS_D]) {

    int best_class = 0;
    int best_distance = TS_D + 1;
    for (int k = 0; k < TS_K; ++k) {
        int distance = 0;
        for (int d = 0; d < TS_D; ++d) {
            distance += (int)query[d] ^ (int)prototypes[k][d];
        }
        if (distance < best_distance) {
            best_distance = distance;
            best_class = k;
        }
    }
    return best_class;
}

int main() {
    static hdc::binary_t sample_codebook[TS_V][TS_D];
    static ap_uint<4> window_indices[TS_W];
    static hdc::binary_t prototypes[TS_K][TS_D];
    static hdc::binary_t query[TS_D];

    for (int v = 0; v < TS_V; ++v) {
        for (int d = 0; d < TS_D; ++d) {
            sample_codebook[v][d] =
                (hdc::binary_t)(((v * 17 + d * 5 + (d >> 1)) >> 2) & 1);
        }
    }

    for (int t = 0; t < TS_W; ++t) {
        window_indices[t] = (ap_uint<4>)((t * 3 + 2) % TS_V);
    }

    encode_window_ref(sample_codebook, window_indices, query);

    const int injected_class = 2;
    for (int k = 0; k < TS_K; ++k) {
        for (int d = 0; d < TS_D; ++d) {
            prototypes[k][d] = (hdc::binary_t)(1 ^ (int)query[d]);
        }
    }
    for (int d = 0; d < TS_D; ++d) {
        prototypes[injected_class][d] = query[d];
    }

    const int expected = search_ref(query, prototypes);
    const int actual = time_series_classification_top(
        sample_codebook, window_indices, prototypes);

    std::printf("Expected label: %d\n", expected);
    std::printf("Actual label:   %d\n", actual);

    if (expected != injected_class) {
        std::printf("FAIL: reference setup expected injected class %d\n",
                    injected_class);
        return 1;
    }
    if (actual != expected) {
        std::printf("FAIL: time-series top disagrees with software reference\n");
        return 1;
    }

    std::printf("== tb_time_series: ALL PASS ==\n");
    return 0;
}
