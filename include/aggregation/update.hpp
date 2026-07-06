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
template <typename proto_t, typename elem_t, int K, int D>
void update(proto_t protos[K][D], const elem_t q[D], int label,
            update_mode_t mode = UPDATE_ADD) {
    // TODO(ADD_SUB / PERCEPTRON): also subtract q from the mispredicted class;
    // requires a predicted-label argument. Baseline handles single-pass ADD.
    (void)mode;
UPDATE_LOOP:
    for (int i = 0; i < D; i++)
        protos[label][i] += (proto_t)q[i];
}

} // namespace hdc

#endif // HDC_UPDATE_HPP
