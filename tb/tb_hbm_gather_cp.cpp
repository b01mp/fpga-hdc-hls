#include <ap_int.h>
#include <hls_stream.h>
#include <cstdio>
#include "common/hdc_types.hpp"
#include "memory/hbm_gather_cp.hpp"

#define TN 64
#define TD 8192

// keep this prototype in sync with top_hbm_gather_cp.cpp
void hbm_gather_cp_top(
        const hdc::hbm_word_t *bank0,
#if HBM_CP >= 2
        const hdc::hbm_word_t *bank1,
#endif
#if HBM_CP >= 4
        const hdc::hbm_word_t *bank2, const hdc::hbm_word_t *bank3,
#endif
#if HBM_CP >= 8
        const hdc::hbm_word_t *bank4, const hdc::hbm_word_t *bank5,
        const hdc::hbm_word_t *bank6, const hdc::hbm_word_t *bank7,
#endif
        int index,
        hls::stream<hdc::hbm_word_t> &out0
#if HBM_CP >= 2
        , hls::stream<hdc::hbm_word_t> &out1
#endif
#if HBM_CP >= 4
        , hls::stream<hdc::hbm_word_t> &out2, hls::stream<hdc::hbm_word_t> &out3
#endif
#if HBM_CP >= 8
        , hls::stream<hdc::hbm_word_t> &out4, hls::stream<hdc::hbm_word_t> &out5
        , hls::stream<hdc::hbm_word_t> &out6, hls::stream<hdc::hbm_word_t> &out7
#endif
        );

static inline int refbit(int c, int row, int dim) {
    return ((c * 7 + row * 131 + dim * 7) >> 1) & 1;   // deterministic per (channel,row,dim)
}

static void fill(hdc::hbm_word_t *bank, int c, int wpr) {
    for (int r = 0; r < TN; r++)
        for (int w = 0; w < wpr; w++) {
            hdc::hbm_word_t word = 0;
            for (int b = 0; b < HBM_WBITS; b++)
                word[b] = refbit(c, r, w * HBM_WBITS + b);
            bank[r * wpr + w] = word;
        }
}

static int check(hls::stream<hdc::hbm_word_t> &s, int c, int idx, int wpr) {
    int e = 0;
    for (int w = 0; w < wpr; w++) {
        hdc::hbm_word_t word = s.read();
        for (int b = 0; b < HBM_WBITS; b++)
            if ((int)word[b] != refbit(c, idx, w * HBM_WBITS + b)) e++;
    }
    return e;
}

int main() {
    const int WPR = TD / HBM_WBITS;
    static hdc::hbm_word_t bank0[TN * (TD / HBM_WBITS)];
#if HBM_CP >= 2
    static hdc::hbm_word_t bank1[TN * (TD / HBM_WBITS)];
#endif
#if HBM_CP >= 4
    static hdc::hbm_word_t bank2[TN * (TD / HBM_WBITS)], bank3[TN * (TD / HBM_WBITS)];
#endif
#if HBM_CP >= 8
    static hdc::hbm_word_t bank4[TN * (TD / HBM_WBITS)], bank5[TN * (TD / HBM_WBITS)];
    static hdc::hbm_word_t bank6[TN * (TD / HBM_WBITS)], bank7[TN * (TD / HBM_WBITS)];
#endif

    fill(bank0, 0, WPR);
#if HBM_CP >= 2
    fill(bank1, 1, WPR);
#endif
#if HBM_CP >= 4
    fill(bank2, 2, WPR); fill(bank3, 3, WPR);
#endif
#if HBM_CP >= 8
    fill(bank4, 4, WPR); fill(bank5, 5, WPR); fill(bank6, 6, WPR); fill(bank7, 7, WPR);
#endif

    int idx = 3;
    hls::stream<hdc::hbm_word_t> out0;
#if HBM_CP >= 2
    hls::stream<hdc::hbm_word_t> out1;
#endif
#if HBM_CP >= 4
    hls::stream<hdc::hbm_word_t> out2, out3;
#endif
#if HBM_CP >= 8
    hls::stream<hdc::hbm_word_t> out4, out5, out6, out7;
#endif

    hbm_gather_cp_top(bank0,
#if HBM_CP >= 2
        bank1,
#endif
#if HBM_CP >= 4
        bank2, bank3,
#endif
#if HBM_CP >= 8
        bank4, bank5, bank6, bank7,
#endif
        idx, out0
#if HBM_CP >= 2
        , out1
#endif
#if HBM_CP >= 4
        , out2, out3
#endif
#if HBM_CP >= 8
        , out4, out5, out6, out7
#endif
        );

    int errs = 0;
    errs += check(out0, 0, idx, WPR);
#if HBM_CP >= 2
    errs += check(out1, 1, idx, WPR);
#endif
#if HBM_CP >= 4
    errs += check(out2, 2, idx, WPR); errs += check(out3, 3, idx, WPR);
#endif
#if HBM_CP >= 8
    errs += check(out4, 4, idx, WPR); errs += check(out5, 5, idx, WPR);
    errs += check(out6, 6, idx, WPR); errs += check(out7, 7, idx, WPR);
#endif

    printf("hbm_gather_cp CP=%d WBITS=%d D=%d: %d errors\n", HBM_CP, HBM_WBITS, TD, errs);
    return errs ? 1 : 0;
}
