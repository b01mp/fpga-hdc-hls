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
 *
 * PER-STAGE PRECISION -- see common/hdc_precision.hpp for the rules.
 *
 *   gen_acc_t   bundle accumulator, holds 0..GEN_W   -> bits_for(GEN_W)
 *   gen_sim_t   Hamming score,      holds 0..GEN_D   -> bits_for(GEN_D) + 1
 *
 * With GEN_W = 8 and GEN_D = 1024 that is 4 bits and 12 bits. The accumulator
 * width is set by how many symbols are bundled; the score width by the size of
 * the hypervector space. The two are unrelated, which is why they are computed
 * separately rather than sharing one datapath width.
 *
 * Override with -DGEN_ACC_BITS / -DGEN_SIM_BITS for the precision sweep.
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "common/hdc_precision.hpp"
#include "application/shared_composition.hpp"

#ifndef GEN_D
#define GEN_D 1024
#endif
#ifndef GEN_W
#define GEN_W 8
#endif
#ifndef GEN_V
#define GEN_V 4
#endif
#ifndef GEN_R
#define GEN_R 64
#endif
#ifndef GEN_DP
#define GEN_DP 8
#endif
#ifndef GEN_CP
#define GEN_CP 2
#endif

// ---- per-stage intermediate widths ----------------------------------------
#ifndef GEN_ACC_BITS
#define GEN_ACC_BITS (hdc::bundle_acc_bits<GEN_W>::value)
#endif
#ifndef GEN_SIM_BITS
#define GEN_SIM_BITS (hdc::hamming_score_bits<GEN_D>::value)
#endif

typedef ap_uint<GEN_ACC_BITS> gen_acc_t;  // bundle accumulator, 0..GEN_W
typedef ap_int <GEN_SIM_BITS> gen_sim_t;  // Hamming-distance accumulator, 0..GEN_D

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
