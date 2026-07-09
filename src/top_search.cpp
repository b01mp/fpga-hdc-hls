/**
 * @file top_search.cpp
 * @brief Concrete synthesis-entry wrapper for the Search category.
 *
 * Fixed-size `set_top` symbol for the search project. C-sim correctness is
 * checked by tb/tb_search.cpp (drives the template directly). No arch pragmas.
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "search/similarity_search.hpp"

#define SRCH_D  256
#define SRCH_K  10
#define SRCH_DP 8     // dimension_parallelism
#define SRCH_CP 2     // class_parallelism (K=10; try 1, 2, 5, 10)
typedef ap_int<32> srch_sim_t;

int search_similarity_top(const hdc::binary_t query[SRCH_D],
                          const hdc::binary_t proto[SRCH_K][SRCH_D]) {
    // memory_space: put the prototypes in BRAM (change impl=BRAM -> URAM to try UltraRAM)
    #pragma HLS bind_storage variable=proto type=RAM_2P impl=BRAM
    return hdc::similarity_search<hdc::binary_t, srch_sim_t, SRCH_D, SRCH_K,
                                  hdc::binary_tag, SRCH_DP, SRCH_CP>(query, proto);
}