/**
 * @file tb_genome.cpp
 * @brief C-simulation testbench for genome_sequence_search_top.
 */

#include <cstdio>
#include <ap_int.h>

#include "common/hdc_types.hpp"

#ifndef GEN_D
#define GEN_D 128
#endif
#ifndef GEN_W
#define GEN_W 8
#endif
#ifndef GEN_V
#define GEN_V 4
#endif
#ifndef GEN_R
#define GEN_R 6
#endif

int genome_sequence_search_top(
    const hdc::binary_t symbol_codebook[GEN_V][GEN_D],
    const ap_uint<4> query_symbols[GEN_W],
    const hdc::binary_t reference_hvs[GEN_R][GEN_D]);

static void encode_genome_ref(
    const hdc::binary_t symbol_codebook[GEN_V][GEN_D],
    const ap_uint<4> query_symbols[GEN_W],
    hdc::binary_t query[GEN_D]) {

    for (int d = 0; d < GEN_D; ++d) {
        int ones = 0;
        for (int w = 0; w < GEN_W; ++w) {
            const int symbol = (int)query_symbols[w];
            const int source = (d - w + GEN_D) % GEN_D;
            ones += (int)symbol_codebook[symbol][source];
        }
        query[d] = (ones * 2 > GEN_W) ? 1 : 0;
    }
}

static int search_ref(
    const hdc::binary_t query[GEN_D],
    const hdc::binary_t references[GEN_R][GEN_D]) {

    int best_reference = 0;
    int best_distance = GEN_D + 1;
    for (int r = 0; r < GEN_R; ++r) {
        int distance = 0;
        for (int d = 0; d < GEN_D; ++d) {
            distance += (int)query[d] ^ (int)references[r][d];
        }
        if (distance < best_distance) {
            best_distance = distance;
            best_reference = r;
        }
    }
    return best_reference;
}

int main() {
    static hdc::binary_t symbol_codebook[GEN_V][GEN_D];
    static ap_uint<4> query_symbols[GEN_W];
    static hdc::binary_t reference_hvs[GEN_R][GEN_D];
    static hdc::binary_t query[GEN_D];

    for (int v = 0; v < GEN_V; ++v) {
        for (int d = 0; d < GEN_D; ++d) {
            symbol_codebook[v][d] =
                (hdc::binary_t)(((v * 19 + d * 7 + (d >> 2)) >> 1) & 1);
        }
    }

    for (int w = 0; w < GEN_W; ++w) {
        query_symbols[w] = (ap_uint<4>)((w + 2) % GEN_V);
    }

    encode_genome_ref(symbol_codebook, query_symbols, query);

    const int injected_reference = 4;
    for (int r = 0; r < GEN_R; ++r) {
        for (int d = 0; d < GEN_D; ++d) {
            reference_hvs[r][d] = (hdc::binary_t)(1 ^ (int)query[d]);
        }
    }
    for (int d = 0; d < GEN_D; ++d) {
        reference_hvs[injected_reference][d] = query[d];
    }

    const int expected = search_ref(query, reference_hvs);
    const int actual = genome_sequence_search_top(
        symbol_codebook, query_symbols, reference_hvs);

    std::printf("Expected reference: %d\n", expected);
    std::printf("Actual reference:   %d\n", actual);

    if (expected != injected_reference) {
        std::printf("FAIL: reference setup expected injected reference %d\n",
                    injected_reference);
        return 1;
    }
    if (actual != expected) {
        std::printf("FAIL: genome top disagrees with software reference\n");
        return 1;
    }

    std::printf("== tb_genome: ALL PASS ==\n");
    return 0;
}
