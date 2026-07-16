/**
 * @file tb_sequence.cpp
 * @brief C-simulation testbench for sequence_classification_top.
 */

#include <cstdio>
#include <ap_int.h>

#include "common/hdc_types.hpp"

#ifndef SEQ_D
#define SEQ_D 128
#endif
#ifndef SEQ_T
#define SEQ_T 6
#endif
#ifndef SEQ_V
#define SEQ_V 12
#endif
#ifndef SEQ_K
#define SEQ_K 4
#endif

int sequence_classification_top(
    const hdc::binary_t token_codebook[SEQ_V][SEQ_D],
    const ap_uint<4> token_indices[SEQ_T],
    const hdc::binary_t prototypes[SEQ_K][SEQ_D]);

static void encode_sequence_ref(
    const hdc::binary_t token_codebook[SEQ_V][SEQ_D],
    const ap_uint<4> token_indices[SEQ_T],
    hdc::binary_t query[SEQ_D]) {

    for (int d = 0; d < SEQ_D; ++d) {
        int ones = 0;
        for (int t = 0; t < SEQ_T; ++t) {
            const int token = (int)token_indices[t];
            const int source = (d - t + SEQ_D) % SEQ_D;
            ones += (int)token_codebook[token][source];
        }
        query[d] = (ones * 2 > SEQ_T) ? 1 : 0;
    }
}

static int search_ref(
    const hdc::binary_t query[SEQ_D],
    const hdc::binary_t prototypes[SEQ_K][SEQ_D]) {

    int best_class = 0;
    int best_distance = SEQ_D + 1;
    for (int k = 0; k < SEQ_K; ++k) {
        int distance = 0;
        for (int d = 0; d < SEQ_D; ++d) {
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
    static hdc::binary_t token_codebook[SEQ_V][SEQ_D];
    static ap_uint<4> token_indices[SEQ_T];
    static hdc::binary_t prototypes[SEQ_K][SEQ_D];
    static hdc::binary_t query[SEQ_D];

    for (int v = 0; v < SEQ_V; ++v) {
        for (int d = 0; d < SEQ_D; ++d) {
            token_codebook[v][d] =
                (hdc::binary_t)(((v * 17 + d * 5 + (d >> 1)) >> 2) & 1);
        }
    }

    for (int t = 0; t < SEQ_T; ++t) {
        token_indices[t] = (ap_uint<4>)((t * 3 + 2) % SEQ_V);
    }

    encode_sequence_ref(token_codebook, token_indices, query);

    const int injected_class = 2;
    for (int k = 0; k < SEQ_K; ++k) {
        for (int d = 0; d < SEQ_D; ++d) {
            prototypes[k][d] = (hdc::binary_t)(1 ^ (int)query[d]);
        }
    }
    for (int d = 0; d < SEQ_D; ++d) {
        prototypes[injected_class][d] = query[d];
    }

    const int expected = search_ref(query, prototypes);
    const int actual = sequence_classification_top(
        token_codebook, token_indices, prototypes);

    std::printf("Expected label: %d\n", expected);
    std::printf("Actual label:   %d\n", actual);

    if (expected != injected_class) {
        std::printf("FAIL: reference setup expected injected class %d\n",
                    injected_class);
        return 1;
    }
    if (actual != expected) {
        std::printf("FAIL: sequence top disagrees with software reference\n");
        return 1;
    }

    std::printf("== tb_sequence: ALL PASS ==\n");
    return 0;
}
