/**
 * @file top_encoding.cpp
 * @brief Concrete synthesis-entry wrapper for the Encoding category.
 *
 * The library primitives are templates (not directly synthesizable tops). This
 * fixed-size wrapper instantiates one at concrete sizes so Vitis HLS has a real
 * `set_top` symbol for the encoding project. C-sim correctness is checked by
 * tb/tb_encoding.cpp (which drives the templates directly); this top is the seam
 * for later csynth / cosim. No architecture pragmas yet (deferred by directive).
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "encoding/bind.hpp"

#define ENC_D  256   // hv_dim
#define ENC_DP 8     // dimension_parallelism (try 1, 4, 8, 16, 32 and compare reports)

void encoding_bind_top(const hdc::binary_t a[ENC_D],
                       const hdc::binary_t b[ENC_D],
                       hdc::binary_t out[ENC_D]) {
    hdc::bind<hdc::binary_t, ENC_D, hdc::binary_tag, ENC_DP>(a, b, out);
}