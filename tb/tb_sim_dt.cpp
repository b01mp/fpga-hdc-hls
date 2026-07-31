/**
 * @file tb_sim_dt.cpp
 * @brief C-sim correctness check for the datatype-parametric streaming search.
 *        Builds random binary queries + references, runs the HW paths, and
 *        compares winner index (and score) against a scalar SW reference.
 *          - binary : Hamming distance, argmin
 *          - integer: dot product (binary query -> +/- ref), argmax
 */
#include <hls_stream.h>
#include <cstdio>
#include <cstdlib>
#include "common/hdc_types.hpp"
#include "search/similarity_search_stream_dt.hpp"

#define TD 1024
#define TNP 6
#define TQB 2
#define TX  32
#define WPRB (TD / HBM_WBITS)          // binary words per HV
#define EI   (HBM_WBITS / TX)          // int elems per word
#define WPRI (TD / EI)                 // int words per reference

void sim_dt_hamming_top(hls::stream<hdc::dt_word_t>&, hls::stream<hdc::dt_word_t>&,
                        hls::stream<hdc::sim_res_t>&);
void sim_dt_dot_top(hls::stream<hdc::dt_word_t>&, hls::stream<hdc::dt_word_t>&,
                    hls::stream<hdc::sim_res_t>&);

int main() {
    srand(7);
    // ---- shared random binary queries and binary references ----
    static int qbit[TQB][TD];
    static int rbin[TNP][TD];
    static int rint[TNP][TD];
    for (int b = 0; b < TQB; b++) for (int d = 0; d < TD; d++) qbit[b][d] = rand() & 1;
    for (int k = 0; k < TNP; k++) for (int d = 0; d < TD; d++) {
        rbin[k][d] = rand() & 1;
        rint[k][d] = (rand() % 2001) - 1000;      // signed ~[-1000,1000]
    }

    int fails = 0;

    // ================= BINARY: Hamming + argmin =================
    {
        hls::stream<hdc::dt_word_t> q, p; hls::stream<hdc::sim_res_t> res;
        for (int b = 0; b < TQB; b++)
            for (int w = 0; w < WPRB; w++) {
                hdc::dt_word_t x = 0;
                for (int i = 0; i < HBM_WBITS; i++) x[i] = qbit[b][w*HBM_WBITS+i];
                q.write(x);
            }
        for (int k = 0; k < TNP; k++)
            for (int w = 0; w < WPRB; w++) {
                hdc::dt_word_t x = 0;
                for (int i = 0; i < HBM_WBITS; i++) x[i] = rbin[k][w*HBM_WBITS+i];
                p.write(x);
            }
        sim_dt_hamming_top(q, p, res);
        for (int b = 0; b < TQB; b++) {
            // SW ref
            int best_d = 1<<30, best_k = 0;
            for (int k = 0; k < TNP; k++) {
                int d = 0;
                for (int i = 0; i < TD; i++) d += (qbit[b][i] ^ rbin[k][i]);
                if (d < best_d) { best_d = d; best_k = k; }
            }
            hdc::sim_res_t r = res.read();
            int hw_k = (int)r.idx, hw_d = (int)r.score;
            bool ok = (hw_k == best_k && hw_d == best_d);
            printf("  [HAM] q%d: HW(k=%d,d=%d) SW(k=%d,d=%d) %s\n",
                   b, hw_k, hw_d, best_k, best_d, ok?"ok":"MISMATCH");
            if (!ok) fails++;
        }
    }

    // ================= INTEGER: dot + argmax =================
    {
        hls::stream<hdc::dt_word_t> q, p; hls::stream<hdc::sim_res_t> res;
        for (int b = 0; b < TQB; b++)
            for (int w = 0; w < WPRB; w++) {
                hdc::dt_word_t x = 0;
                for (int i = 0; i < HBM_WBITS; i++) x[i] = qbit[b][w*HBM_WBITS+i];
                q.write(x);
            }
        for (int k = 0; k < TNP; k++)
            for (int w = 0; w < WPRI; w++) {
                hdc::dt_word_t x = 0;
                for (int j = 0; j < EI; j++) {
                    ap_int<TX> v = rint[k][w*EI+j];
                    x.range((j+1)*TX-1, j*TX) = (ap_uint<TX>)v;
                }
                p.write(x);
            }
        sim_dt_dot_top(q, p, res);
        for (int b = 0; b < TQB; b++) {
            long best_s = -(1L<<60); int best_k = 0;
            for (int k = 0; k < TNP; k++) {
                long s = 0;
                for (int i = 0; i < TD; i++) s += qbit[b][i] ? rint[k][i] : -rint[k][i];
                if (s > best_s) { best_s = s; best_k = k; }
            }
            hdc::sim_res_t r = res.read();
            int hw_k = (int)r.idx; long hw_s = (long)r.score;
            bool ok = (hw_k == best_k && hw_s == best_s);
            printf("  [DOT] q%d: HW(k=%d,s=%ld) SW(k=%d,s=%ld) %s\n",
                   b, hw_k, hw_s, best_k, best_s, ok?"ok":"MISMATCH");
            if (!ok) fails++;
        }
    }

    printf(fails ? "\nFAIL: %d mismatch(es)\n" : "\nPASS: all correct\n", fails);
    return fails ? 1 : 0;
}
