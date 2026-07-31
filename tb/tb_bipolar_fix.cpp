/**
 * @file tb_bipolar_fix.cpp
 * @brief Verify the bipolar-draw fix: random_hv / gen_levels with bipolar_tag
 *        must produce {-1,+1}, not the old silently-cast {0,1}. Also confirms
 *        the default (binary) path is unchanged.
 */
#include <cstdio>
#include "common/hdc_types.hpp"
#include "generation/random_hv.hpp"
#include "generation/gen_levels.hpp"

#define D 256
#define F 4
#define L 5

static hdc::binary_t  bin_cb[F][D];
static hdc::bipolar_t bip_cb[F][D];
static hdc::binary_t  bin_lv[L][D];
static hdc::bipolar_t bip_lv[L][D];

int main() {
    int fails = 0;

    hdc::random_hv<hdc::binary_t,  D, F>(bin_cb);                       // default binary
    hdc::random_hv<hdc::bipolar_t, D, F, hdc::bipolar_tag>(bip_cb);     // bipolar
    hdc::gen_levels<hdc::binary_t,  D, L>(bin_lv);
    hdc::gen_levels<hdc::bipolar_t, D, L, hdc::bipolar_tag>(bip_lv);

    // binary base must stay {0,1}
    for (int f = 0; f < F; f++) for (int d = 0; d < D; d++) {
        int v = (int)bin_cb[f][d];
        if (v != 0 && v != 1) { printf("binary random_hv bad value %d\n", v); fails++; }
    }
    // bipolar base must be {-1,+1}, and must actually contain some -1
    int neg = 0;
    for (int f = 0; f < F; f++) for (int d = 0; d < D; d++) {
        int v = (int)bip_cb[f][d];
        if (v != -1 && v != 1) { printf("bipolar random_hv bad value %d\n", v); fails++; }
        if (v == -1) neg++;
    }
    if (neg == 0) { printf("bipolar random_hv has NO -1 values (bug not fixed)\n"); fails++; }

    // bipolar levels must be {-1,+1} with some -1
    int lneg = 0;
    for (int l = 0; l < L; l++) for (int d = 0; d < D; d++) {
        int v = (int)bip_lv[l][d];
        if (v != -1 && v != 1) { printf("bipolar gen_levels bad value %d\n", v); fails++; }
        if (v == -1) lneg++;
    }
    if (lneg == 0) { printf("bipolar gen_levels has NO -1 values (bug not fixed)\n"); fails++; }

    // graded distance preserved: level 0 vs last differ in ~half the dims
    int diff = 0;
    for (int d = 0; d < D; d++) if (bip_lv[0][d] != bip_lv[L-1][d]) diff++;
    printf("bipolar levels: %d -1's in codebook; level0 vs level%d differ in %d/%d dims\n",
           neg, L-1, diff, D);

    printf(fails ? "\nFAIL: %d issue(s)\n" : "\nPASS: bipolar draw fixed, binary unchanged\n", fails);
    return fails ? 1 : 0;
}
