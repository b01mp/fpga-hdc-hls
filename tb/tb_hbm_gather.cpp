#include <ap_int.h>
#include <cstdio>
#include "common/hdc_types.hpp"
#include "memory/hbm_gather.hpp"

#define TN 128
#define TD 1024

// keep this prototype in sync with top_hbm_gather.cpp
void hbm_gather_top(const hdc::hbm_word_t *codebook, int index, hdc::binary_t out[TD]);

int main() {
    const int WPR = TD / HBM_WBITS;      // packed words per row

    // reference codebook (deterministic bits)
    static hdc::binary_t ref[TN][TD];
    for (int r = 0; r < TN; r++)
        for (int i = 0; i < TD; i++)
            ref[r][i] = (hdc::binary_t)(((r * 131 + i * 7) >> 1) & 1);

    // pack each row into WPR wide words, flat layout [N*WPR]
    static hdc::hbm_word_t codebook[TN * WPR];
    for (int r = 0; r < TN; r++)
        for (int w = 0; w < WPR; w++) {
            hdc::hbm_word_t word = 0;
            for (int b = 0; b < HBM_WBITS; b++)
                word[b] = ref[r][w * HBM_WBITS + b];
            codebook[r * WPR + w] = word;
        }

    int idx = 42;
    hdc::binary_t out[TD];
    hbm_gather_top(codebook, idx, out);

    int errs = 0;
    for (int i = 0; i < TD; i++) if (out[i] != ref[idx][i]) errs++;
    printf("hbm_gather (streaming) WBITS=%d WPR=%d: %d errors\n", HBM_WBITS, WPR, errs);
    return errs ? 1 : 0;
}
