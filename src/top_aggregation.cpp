/**
 * @file top_aggregation.cpp
 * @brief Concrete synthesis-entry wrapper for the Aggregation & Update category.
 *
 * Fixed-size `set_top` symbol for the aggregation project. C-sim correctness is
 * checked by tb/tb_aggregation.cpp (drives templates directly). No arch pragmas.
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "aggregation/threshold.hpp"

#define AGG_D 256                 // hv_dim (representative)
typedef ap_int<32> agg_acc_t;     // accumulator_bits = 32

void aggregation_threshold_top(const agg_acc_t acc[AGG_D],
                               hdc::binary_t out[AGG_D],
                               int count) {
    hdc::threshold<agg_acc_t, hdc::binary_t, AGG_D>(acc, out, count);
}
