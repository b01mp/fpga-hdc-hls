/**
 * @file top_onchip_search.cpp
 * @brief ON-CHIP composed similarity search -- the capacity-crossover baseline.
 *
 * MIRROR of top_compose_biohd.cpp. Same D, same reference count, same query
 * batch, same metric dispatch, same packed 512-bit word layout, same search
 * primitive structure. The ONE difference: the reference library lives in an
 * on-chip array instead of behind an m_axi master. That is the variable under
 * test -- the memory tier.
 *
 * This is what prior FPGA-HDC frameworks are. Hyle states the assumption
 * explicitly (hypervectors in BRAM, single-cycle access, so memory never enters
 * the measurement); F5-HD and AeneasHDC hold class hypervectors in BRAM too.
 * The point of the crossover experiment is that this design has a hard ceiling:
 * once K x D x X exceeds on-chip capacity it cannot be built at all, while the
 * streaming design keeps going.
 *
 * WHY THE LOAD PATH EXISTS. The codebook is a local static array, not a
 * top-level port, because HLS does NOT count the memory behind an ap_memory
 * PORT in the resource report -- that memory is external to the block. A local
 * array is instantiated and reported, which is exactly the number the crossover
 * needs. The `load` mode writes it from off-chip once; without a writer, an
 * uninitialised read-only array can be constant-folded away and the BRAM would
 * vanish from the report. Loading is a one-time cost amortised over many
 * queries -- the same assumption prior work makes -- so the search-mode latency
 * is the number to compare.
 *
 * Swept over precision (ONC_X) x reference count (ONC_K) by
 * scripts/sweep_capacity.tcl.
 *
 *   ONC_X = 1  : binary library, Hamming distance, argmin
 *   ONC_X = 8  : int8 library,  dot product, argmax
 *   ONC_X = 32 : int32 library, dot product, argmax  (the BioHD anchor)
 *
 * The query is binary in every config, so the dot product is a conditional
 * add/subtract with no multiplier -- matching the streaming path exactly.
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "search/similarity_search_onchip.hpp"

#ifndef ONC_D
#define ONC_D 10240          // hv dimensions (BioHD anchor, 10k padded to 512)
#endif
#ifndef ONC_X
#define ONC_X 1              // element width: 1 = binary, 8 = int8, 32 = int32
#endif
#ifndef ONC_K
#define ONC_K 64             // reference hypervectors resident on chip
#endif
#ifndef ONC_QB
#define ONC_QB 4             // resident query batch
#endif

// words per reference, total codebook words, query words (query is binary)
#define ONC_REF_WORDS   ((ONC_D * ONC_X) / HBM_WBITS)
#define ONC_TOTAL_WORDS (ONC_K * ONC_REF_WORDS)
#define ONC_QWORDS      (ONC_D / HBM_WBITS)

#if ONC_X == 1
typedef hdc::binary_tag  onc_family_t;
#else
typedef hdc::integer_tag onc_family_t;
#endif

void onchip_search_top(
        const hdc::dt_word_t *src,                        // codebook source (load only)
        int load,                                          // 1 = load, 0 = search
        const hdc::dt_word_t qin[ONC_QB * ONC_QWORDS],
        int out_id[ONC_QB], ap_int<48> out_score[ONC_QB]) {
    #pragma HLS INTERFACE m_axi port=src offset=slave bundle=gmem0 num_read_outstanding=16 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=load
    #pragma HLS INTERFACE ap_memory port=qin
    #pragma HLS INTERFACE ap_memory port=out_id
    #pragma HLS INTERFACE ap_memory port=out_score
    #pragma HLS INTERFACE s_axilite port=return
    #pragma HLS ARRAY_PARTITION variable=out_id    complete dim=1
    #pragma HLS ARRAY_PARTITION variable=out_score complete dim=1

    // The resident reference library. This is the object whose size decides
    // whether the design fits at all -- K * D * X bits.
    static hdc::dt_word_t codebook[ONC_TOTAL_WORDS];
    #pragma HLS BIND_STORAGE variable=codebook type=ram_2p impl=bram

    if (load) {
    LOAD_CB:
        for (int i = 0; i < ONC_TOTAL_WORDS; i++) {
            #pragma HLS PIPELINE II=1
            codebook[i] = src[i];
        }
    } else {
        hdc::sim_res_t r[ONC_QB];
        #pragma HLS ARRAY_PARTITION variable=r complete dim=1

        hdc::similarity_search_onchip<ONC_D, ONC_K, ONC_QB, ONC_X>(
            codebook, 0, qin, r, onc_family_t());

    EMIT:
        for (int b = 0; b < ONC_QB; b++) {
            #pragma HLS PIPELINE II=1
            out_id[b]    = (int)r[b].idx;
            out_score[b] = r[b].score;
        }
    }
}
