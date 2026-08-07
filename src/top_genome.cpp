/**
 * @file top_genome.cpp
 * @brief Paper application: genome-sequence search composition.
 *
 * Data path for one ordered DNA window:
 *
 *   gather(symbol/k-mer) -> permute(position) -> bundle  (repeat GEN_W times)
 *                         -> threshold -> similarity_search -> reference id
 *
 * The current primitive library exposes argmin similarity search. Thresholded
 * search and early termination can be layered on top once the basic U280
 * implementation evidence is collected.
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "application/shared_composition.hpp"

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
#ifndef GEN_DP
#define GEN_DP 8
#endif
#ifndef GEN_CP
#define GEN_CP 2
#endif

typedef ap_uint<4> gen_acc_t;  // enough for GEN_W <= 15
typedef ap_int<32> gen_sim_t;

int genome_sequence_search_top(
    const hdc::binary_t symbol_codebook[GEN_V][GEN_D],
    const ap_uint<4> query_symbols[GEN_W],
    const hdc::binary_t reference_hvs[GEN_R][GEN_D]) {

    hdc::binary_t query_hv[GEN_D];
    #pragma HLS ARRAY_PARTITION variable=query_hv cyclic factor=GEN_DP dim=1

    hdc_app::encode_ordered_window_query<GEN_D, GEN_W, GEN_V, GEN_DP,
                                         gen_acc_t>(
        symbol_codebook, query_symbols, query_hv);

    return hdc_app::search_binary_references<GEN_D, GEN_R, GEN_DP, GEN_CP,
                                             gen_sim_t>(
        query_hv, reference_hvs);
}
