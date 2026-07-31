/**
 * @file update.hpp   (Aggregation & Update)
 * @brief FUNCTION: update  --  (protos, q, label) -> protos  (signed accumulate).
 *
 *   Contract:      (protos[K][D], q[D], label) -> protos   (update prototype state)
 *   App (exposed):  update_mode, prototype datatype, accumulator datatype
 *                   (+ template: learning_rate, retrain_epochs)
 *   Arch (deferred): dimension_parallelism, memory_space, pipeline_mode
 *
 * UPDATE_ADD (baseline): superpose q into prototype[label] (single-pass learning).
 * UPDATE_ADD_SUB / PERCEPTRON (retraining) also SUBTRACT q from the mispredicted
 * class -- that needs the *predicted* label too, so the signature will gain a
 * `pred_label` argument when those modes are implemented.
 *
 * STATUS: skeleton -- UPDATE_ADD implemented; ADD_SUB/PERCEPTRON = TODO.
 */
#ifndef HDC_UPDATE_HPP
#define HDC_UPDATE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// proto_t = prototype/state datatype, elem_t = query element datatype.
// K = num_prototypes, D = hv_dim.
template <typename proto_t, typename elem_t, int K, int D, int DP = 1>
void update(proto_t protos[K][D], const elem_t q[D], int label,
            update_mode_t mode = UPDATE_ADD) {
    #pragma HLS ARRAY_PARTITION variable=protos type=cyclic factor=DP dim=2
    #pragma HLS ARRAY_PARTITION variable=q      type=cyclic factor=DP dim=1
    (void)mode;   // ADD_SUB / PERCEPTRON need a pred_label arg (deferred)
UPDATE_LOOP:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        protos[label][i] += (proto_t)q[i];
    }
}
}
#endif // HDC_UPDATE_HPP
