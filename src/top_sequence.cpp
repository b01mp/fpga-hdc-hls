/**
 * @file top_sequence.cpp
 * @brief Temporal / n-gram style HDC sequence-classification composition.
 *
 * Data path for one token sequence:
 *
 *   gather(token) -> permute(position) -> bundle  (repeat SEQ_T times)
 *                  -> threshold -> similarity_search -> predicted class
 *
 * This exercises the memory, encoding, aggregation, and search library stages
 * with a different application shape from image_classification_top.
 */

#include <ap_int.h>

#include "common/hdc_types.hpp"
#include "memory/gather.hpp"
#include "encoding/permute.hpp"
#include "aggregation/bundle.hpp"
#include "aggregation/threshold.hpp"
#include "search/similarity_search.hpp"

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
#ifndef SEQ_DP
#define SEQ_DP 8
#endif
#ifndef SEQ_CP
#define SEQ_CP 2
#endif

typedef ap_uint<4> seq_acc_t;  // enough for SEQ_T <= 15
typedef ap_int<32> seq_sim_t;

int sequence_classification_top(
    const hdc::binary_t token_codebook[SEQ_V][SEQ_D],
    const ap_uint<4> token_indices[SEQ_T],
    const hdc::binary_t prototypes[SEQ_K][SEQ_D]) {

    hdc::binary_t token_hv[SEQ_D];
    hdc::binary_t positional_hv[SEQ_D];
    seq_acc_t acc[SEQ_D];
    hdc::binary_t query_hv[SEQ_D];

    #pragma HLS ARRAY_PARTITION variable=token_hv      cyclic factor=SEQ_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=positional_hv cyclic factor=SEQ_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=acc           cyclic factor=SEQ_DP dim=1
    #pragma HLS ARRAY_PARTITION variable=query_hv      cyclic factor=SEQ_DP dim=1

INIT_ACC:
    for (int d = 0; d < SEQ_D; ++d) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=SEQ_DP
        acc[d] = 0;
    }

TOKEN_LOOP:
    for (int t = 0; t < SEQ_T; ++t) {
        const int token = (int)token_indices[t];
        hdc::gather<hdc::binary_t, SEQ_V, SEQ_D, SEQ_DP>(
            token_codebook, token, token_hv);

        hdc::permute<hdc::binary_t, SEQ_D, SEQ_DP>(
            token_hv, t, positional_hv);

        hdc::bundle<hdc::binary_t, seq_acc_t, SEQ_D, SEQ_DP>(
            positional_hv, acc);
    }

    hdc::threshold<seq_acc_t, hdc::binary_t, SEQ_D,
                   hdc::binary_tag, SEQ_DP>(
        acc, query_hv, SEQ_T, hdc::TIE_SET_ZERO);

    return hdc::similarity_search<hdc::binary_t, seq_sim_t, SEQ_D, SEQ_K,
                                  hdc::binary_tag, SEQ_DP, SEQ_CP>(
        query_hv, prototypes, hdc::SIM_HAMMING, hdc::SEARCH_ARGMIN);
}
