/**
 * @file similarity_search.hpp   (Search)
 * @brief FUNCTION: similarity_search  --  (query, protos[K][D]) -> index.
 *
 *   Contract:      compare query to K prototypes -> best index (or index[top_k]/(index,score))
 *   App (exposed):  num_prototypes (K), similarity datatype, similarity_metric,
 *                   search_mode, early_termination, top_k, hv_dim (D)
 *   Arch (deferred): class_parallelism, dimension_parallelism, memory_space, banking_factor
 *
 * Datatype-parametric (Novelty 1): the metric datapath AND the search direction
 * are selected at COMPILE time by a family tag -- Hamming distance + argmin
 * (binary), dot-product similarity + argmax (bipolar/fixed/integer/pow2). The
 * runtime metric/mode args are kept for signature compatibility but the family
 * drives the behavior.
 *
 * NOTE: top_k / thresholded / early_termination modes are still deferred.
 *
 * STATUS: datatype-parametric (binary=Hamming, others=dot) + C-sim tested.
 */
#ifndef HDC_SIMILARITY_SEARCH_HPP
#define HDC_SIMILARITY_SEARCH_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// --- Per-family per-element score contribution (accumulated into sim_t) ---
//   binary : XOR  -> accumulates a Hamming DISTANCE     (lower  = more similar)
//   others : a*b  -> accumulates a dot-product SIMILARITY (higher = more similar)
//   pow2   : the product of two signed powers of two is itself a signed power of
//            two (sign XOR, exponent ADD), which is then DECODED to a linear
//            value so it can be summed. Multiply-free: an adder plus a shift,
//            never a DSP. Summing the exponents directly would be wrong --
//            2^a + 2^b is not a power of two.
template <typename S, typename T> inline S sim_elem(T a, T b, binary_tag)  { return (S)(a ^ b); }
template <typename S, typename T> inline S sim_elem(T a, T b, bipolar_tag) { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, fixed_tag)   { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, integer_tag) { return (S)(a * b); }
template <typename S, typename T> inline S sim_elem(T a, T b, pow2_tag) {
    // NOTE: deliberately NOT routed through pow2_bind(), which saturates the
    // exponent to fit a pow2_t. The product is only ever consumed as a linear
    // value here, so the exponent sum is taken at full width. The caller must
    // size S for (max product exponent + log2(D)) headroom.
    pow2_t pa = (pow2_t)a, pb = (pow2_t)b;
    int k = (int)pow2_exp(pa) + (int)pow2_exp(pb);
    S mag = (S)(((S)1) << k);
    return (pow2_sign(pa) ^ pow2_sign(pb)) ? (S)(-mag) : mag;
}

// --- Per-family search direction: is a LARGER accumulated score "more similar"? ---
inline bool sim_higher_better(binary_tag)  { return false; }  // Hamming distance: minimize
inline bool sim_higher_better(bipolar_tag) { return true;  }  // dot product:     maximize
inline bool sim_higher_better(fixed_tag)   { return true;  }
inline bool sim_higher_better(integer_tag) { return true;  }
inline bool sim_higher_better(pow2_tag)    { return true;  }

// elem_t = element datatype, sim_t = score datatype, D = hv_dim, K = num_prototypes,
// Family = datatype-family tag, DP = dimension_parallelism, CP = class_parallelism.
template <typename elem_t, typename sim_t, int D, int K,
          typename Family = binary_tag, int DP = 1, int CP = 1>
int similarity_search(const elem_t query[D], const elem_t proto[K][D],
                      sim_metric_t metric = SIM_HAMMING,
                      search_mode_t mode  = SEARCH_ARGMAX,
                      sim_t *best_score_out = 0) {
    #pragma HLS ARRAY_PARTITION variable=query type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=proto type=cyclic factor=CP dim=1
    #pragma HLS ARRAY_PARTITION variable=proto type=cyclic factor=DP dim=2
    (void)metric; (void)mode;                      // family selects metric + direction
    const bool higher_better = sim_higher_better(Family());

    // ---- STRUCTURE NOTE: why the class loop is not simply UNROLLed ---------
    //
    // The obvious way to spend CP is `for c: #pragma HLS UNROLL factor=CP` with
    // a PIPELINE'd dimension loop inside it. That is what this function used to
    // do, and measurement on the U280 showed it does not work:
    //
    //   D=10240, DP=1, KP in {64, 256, 1024}, CP 1 -> 8
    //     speedup   1.00x  (latency got marginally WORSE)
    //     LUT       3.9x
    //     efficiency 0.12, identical at all three KP
    //
    // 16x more classes to divide changed nothing, so a shortage of work was
    // never the cause. Two things were wrong:
    //
    //   1. UNROLL on an OUTER loop whose body holds a PIPELINE'd inner loop
    //      replicates the datapath but schedules the copies in sequence. Vitis
    //      then flattens the pair into one loop -- the reports name it
    //      SEARCH_CLASSES_SEARCH_DIM -- at which point the outer unroll factor
    //      has nothing left to apply to.
    //
    //   2. Every replicated lane reads the SAME query[i] in the same cycle.
    //      `query` is partitioned by DP, not by CP, so CP lanes contend for one
    //      memory's ports. Adding lanes to a port-limited loop adds area, not
    //      throughput.
    //
    // The fix is a loop interchange. The DIMENSION loop becomes the pipelined
    // one and the CLASS loop moves inside it and is fully unrolled, so:
    //
    //   * query[i] is read ONCE per cycle and broadcast to all CP lanes --
    //     no port contention, because there is only one reader.
    //   * proto[] is already ARRAY_PARTITION'd cyclic by CP on dim 1, and the
    //     lanes in a group are consecutive classes cb..cb+CP-1, so each lane
    //     lands in its own bank.
    //   * each lane keeps a private accumulator, so there is no shared
    //     running total inside the hot loop.
    //
    // The argmin/argmax fold happens once per GROUP of CP classes, not once per
    // cycle, so the cross-lane comparison chain costs CP compares per D cycles
    // of work rather than sitting on the critical path.
    //
    // BEHAVIOUR IS UNCHANGED. Ties still resolve to the lowest class index:
    // groups are visited in increasing cb, lanes in increasing p, and the
    // comparison is strict, so an equal score never displaces an earlier one.
    // At CP=1 this reduces to K sequential passes over D -- the same schedule
    // the previous version produced -- so existing CP=1 measurements remain
    // valid and do not need re-collecting.

    sim_t best_score = 0;
    int   best_idx   = 0;

CLASS_GROUP:
    for (int cb = 0; cb < K; cb += CP) {
        sim_t acc[CP];
        #pragma HLS ARRAY_PARTITION variable=acc complete dim=1

    ACC_INIT:
        for (int p = 0; p < CP; p++) {
            #pragma HLS UNROLL
            acc[p] = 0;
        }

        // The pipelined loop. One query element per cycle (times DP), fanned
        // out to every class lane.
    SEARCH_DIM:
        for (int i = 0; i < D; i++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL   factor=DP
            elem_t q = query[i];                   // single read, broadcast
        CLASS_LANE:
            for (int p = 0; p < CP; p++) {
                #pragma HLS UNROLL
                int c = cb + p;
                if (c < K) acc[p] += sim_elem<sim_t>(q, proto[c][i], Family());
            }
        }

        // Fold this group's CP partial scores into the running best. `first`
        // seeds the comparison without needing a +/-inf initial value, which
        // would differ per metric family.
    FOLD:
        for (int p = 0; p < CP; p++) {
            #pragma HLS UNROLL
            int c = cb + p;
            if (c < K) {
                bool first  = (cb == 0 && p == 0);
                bool better = higher_better ? (acc[p] > best_score)
                                            : (acc[p] < best_score);
                if (first || better) { best_score = acc[p]; best_idx = c; }
            }
        }
    }

    if (best_score_out) *best_score_out = best_score;
    return best_idx;
}

} // namespace hdc

#endif // HDC_SIMILARITY_SEARCH_HPP
