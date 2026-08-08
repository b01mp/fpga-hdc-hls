/**
 * @file top_characterize.cpp
 * @brief One concrete top per synthesizable library function, for the parallelism
 *        characterization sweep. All share the CH_DP / CH_FP / CH_CP knobs, which
 *        the sweep overrides via -D. Binary datatype (the datatype dimension is
 *        characterized separately in top_datatype.cpp). Generation is offline.
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "encoding/bind.hpp"
#include "encoding/permute.hpp"
#include "encoding/scale.hpp"
#include "encoding/gemm.hpp"
#include "encoding/matvec.hpp"
#include "encoding/transpose.hpp"
#include "encoding/flatten.hpp"
#include "aggregation/bundle.hpp"
#include "aggregation/threshold.hpp"
#include "aggregation/normalize.hpp"
#include "aggregation/cast.hpp"
#include "aggregation/update.hpp"
#include "search/similarity_search.hpp"
#include "memory/gather.hpp"
#include "memory/place.hpp"
#include "control/convergence_check.hpp"
#include "control/initialize_centroids.hpp"

#ifndef CH_DP
#define CH_DP 1
#endif
#ifndef CH_FP
#define CH_FP 1
#endif
#ifndef CH_CP
#define CH_CP 1
#endif

// ---- Problem size ----------------------------------------------------------
// D and KP were fixed constants until the CP diagnostic needed to vary them.
// They are now -D overridable with the ORIGINAL values as defaults, so every
// existing sweep and every already-collected row stays bit-identical: a run
// with no -DCH_D / -DCH_KP still compiles D=256, KP=10.
//
// WHY KP HAD TO BECOME A KNOB. The CP (class_parallelism) numbers in
// master_table.csv were all measured at KP=10. CP=8 on a 10-iteration class
// loop leaves almost nothing to divide, so a flat CP curve there is ambiguous:
// it could be the loop structure, or it could just be too few classes.
// Sweeping KP separates the two explanations.
#ifndef CH_D
#define CH_D  256     // hv_dim
#endif
#ifndef CH_KP
#define CH_KP 10      // num_prototypes
#endif

#define D    CH_D
#define KP   CH_KP
#define NCB  64       // codebook / sample rows
#define MF   64       // features / matrix dim (gemm/matvec)

typedef hdc::binary_t bt;          // binary element
typedef ap_int<32>    acct;        // accumulator
typedef ap_int<8>     i8;          // integer element (projection / scale / normalize)

// ---- Encoding ----
void ch_bind(const bt a[D], const bt b[D], bt out[D]) {
    hdc::bind<bt, D, hdc::binary_tag, CH_DP>(a, b, out);
}
void ch_permute(const bt in[D], int shift, bt out[D]) {
    hdc::permute<bt, D, CH_DP>(in, shift, out);
}
void ch_scale(const i8 in[D], int w, i8 out[D]) {
    hdc::scale<i8, int, D, CH_DP>(in, w, out);
}
void ch_gemm(const i8 A[MF][MF], const i8 B[MF][MF], acct C[MF][MF]) {
    hdc::gemm<i8, acct, MF, MF, MF, CH_DP, CH_FP>(A, B, C);
}
void ch_matvec(const i8 A[D][MF], const i8 x[MF], acct y[D]) {
    hdc::matvec<i8, acct, D, MF, CH_DP, CH_FP>(A, x, y);
}
void ch_transpose(const bt in[MF][D], bt out[D][MF]) {
    hdc::transpose<bt, MF, D, CH_DP>(in, out);
}
void ch_flatten(const bt in[MF][D], bt out[MF * D]) {
    hdc::flatten<bt, MF, D, CH_DP>(in, out);
}

// ---- Aggregation ----
void ch_bundle(const bt in[D], acct acc[D]) {
    hdc::bundle<bt, acct, D, CH_DP>(in, acc);
}
void ch_threshold(const acct acc[D], bt out[D], int count) {
    hdc::threshold<acct, bt, D, hdc::binary_tag, CH_DP>(acc, out, count);
}
void ch_normalize(const i8 in[D], i8 out[D]) {
    hdc::normalize<i8, acct, D, CH_DP>(in, out);
}
void ch_cast(const acct in[D], bt out[D]) {
    hdc::cast<acct, bt, D, CH_DP>(in, out);
}
void ch_update(acct protos[KP][D], const bt q[D], int label) {
    hdc::update<acct, bt, KP, D, CH_DP>(protos, q, label);
}

// ---- Search ----
int ch_similarity(const bt query[D], const bt proto[KP][D]) {
    return hdc::similarity_search<bt, acct, D, KP, hdc::binary_tag, CH_DP, CH_CP>(query, proto);
}

// ---- Memory ----
void ch_gather(const bt codebook[NCB][D], int index, bt out[D]) {
    hdc::gather<bt, NCB, D, CH_DP>(codebook, index, out);
}
void ch_place(const bt in[NCB][D], bt out[NCB][D]) {
    hdc::place<bt, NCB, D, CH_DP>(in, out);
}

// ---- Control ----
bool ch_convergence(const bt nw[KP][D], const bt old[KP][D]) {
    return hdc::convergence_check<bt, KP, D, CH_DP, CH_CP>(nw, old, 0);
}
void ch_init_centroids(const bt samples[NCB][D], bt centroids[KP][D]) {
    hdc::initialize_centroids<bt, bt, NCB, KP, D, CH_DP>(samples, centroids, hdc::CINIT_SAMPLE);
}
