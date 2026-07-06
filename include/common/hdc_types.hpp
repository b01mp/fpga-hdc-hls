/**
 * @file hdc_types.hpp
 * @brief Shared datatypes and mode enums for the FPGA-HDC primitive library.
 *
 * The library is datatype-parametric: every primitive takes its element/accum/
 * similarity datatype as a C++ `typename` template argument, and its sizes
 * (hv_dim, num_features, num_levels, num_prototypes, ...) as `int` template
 * arguments. That is how the APPLICATION parameters from the parameter table are
 * "wired as inputs" to each function -- no application-specific constants live
 * inside a primitive (compare the emg_hdc baseline, which fixed these via a
 * config header). Nothing here forces a width; callers pick the concrete type.
 *
 * The enums below are the *mode* application-parameters (level_mode,
 * similarity_metric, search_mode, update_mode, ...): passed as ordinary function
 * arguments so a testbench can exercise each setting.
 *
 * NOTE (architecture-level, deferred): no HLS pragmas (PIPELINE/UNROLL/INLINE/
 * ARRAY_PARTITION/bind_storage) appear anywhere in this library yet. Those are
 * the architecture parameters and get added in a later step once the app-param
 * templates are C-sim verified. Loops are written plainly for now.
 */

#ifndef HDC_TYPES_HPP
#define HDC_TYPES_HPP

#include <ap_int.h>
#include <ap_fixed.h>

namespace hdc {

// ---- Convenience element aliases (callers may also pass any ap_* type) ------
typedef ap_uint<1> binary_t;     // element_bits = 1  (binary HV element)
// bipolar / fixed-point elements are just e.g. ap_int<2>, ap_int<8>, ap_fixed<..>

// ---- Mode application-parameters (passed as function arguments) -------------

// threshold_tie: how threshold() breaks an exact count/2 tie.
enum tie_policy_t { TIE_SET_ZERO = 0, TIE_SET_ONE = 1 };

// level_mode: inter-level correlation policy for gen_levels().
enum level_mode_t { LEVEL_LINEAR = 0, LEVEL_APPROX_LINEAR = 1, LEVEL_THERMOMETER = 2 };

// similarity_metric: distance/similarity datapath in similarity_search().
enum sim_metric_t { SIM_HAMMING = 0, SIM_COSINE = 1, SIM_DOT = 2 };

// search_mode: how a winner is picked from the per-class scores.
enum search_mode_t { SEARCH_ARGMAX = 0, SEARCH_ARGMIN = 1, SEARCH_TOPK = 2, SEARCH_THRESHOLDED = 3 };

// update_mode: prototype state update rule in update().
enum update_mode_t { UPDATE_ADD = 0, UPDATE_ADD_SUB = 1, UPDATE_PERCEPTRON = 2 };

// centroid_init_mode: seeding policy for initialize_centroids().
enum centroid_init_t { CINIT_RANDOM = 0, CINIT_SAMPLE = 1 };

} // namespace hdc

#endif // HDC_TYPES_HPP
