/**
 * @file tb_encoding.cpp
 * @brief C-sim testbench for the Encoding category (tested primitives).
 *
 * Covers the ported-and-verified primitives: quantize, bind.
 * (permute/scale/gemm/matvec/transpose/flatten have reference bodies but are not
 *  asserted here yet -- add cases as they are reviewed.)
 *
 * Self-contained: synthetic inputs + golden checks, no external data. Returns
 * non-zero on any mismatch so csim_design reports failure.
 */
#include <cstdio>
#include <ap_int.h>
#include "encoding/quantize.hpp"
#include "encoding/bind.hpp"

using hdc::binary_t;

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("  FAIL: %s\n", msg); failures++; } } while (0)

int main() {
    std::printf("== tb_encoding ==\n");

    // ---- quantize<feat=float, idx=int, L=8> over [0,10] -------------------
    {
        const int L = 8;
        // NOTE: parenthesize conditions holding template<...> commas so the
        // preprocessor does not split them as extra CHECK() macro arguments.
        CHECK((hdc::quantize<float,int,L>(0.0f, 0.0f, 10.0f) == 0),      "quantize min -> 0");
        CHECK((hdc::quantize<float,int,L>(10.0f, 0.0f, 10.0f) == L-1),   "quantize max -> L-1");
        CHECK((hdc::quantize<float,int,L>(-5.0f, 0.0f, 10.0f) == 0),     "quantize below-range clamps");
        CHECK((hdc::quantize<float,int,L>(99.0f, 0.0f, 10.0f) == L-1),   "quantize above-range clamps");
        // value 5.0 in [0,10] -> norm 0.5 -> bucket floor(0.5*8)=4
        CHECK((hdc::quantize<float,int,L>(5.0f, 0.0f, 10.0f) == 4),      "quantize midpoint -> 4");
        // monotonic non-decreasing across the range
        int prev = -1; bool mono = true;
        for (int s = 0; s <= 100; s++) {
            int q = hdc::quantize<float,int,L>(s * 0.1f, 0.0f, 10.0f);
            if (q < prev) mono = false; prev = q;
        }
        CHECK(mono, "quantize monotonic over range");
    }

    // ---- bind<binary, D=16> : XOR --------------------------------------
    {
        const int D = 16;
        binary_t a[D], b[D], out[D];
        for (int i = 0; i < D; i++) { a[i] = i & 1; b[i] = (i >> 1) & 1; }
        hdc::bind<binary_t, D>(a, b, out);
        bool ok = true;
        for (int i = 0; i < D; i++) if (out[i] != (binary_t)(a[i] ^ b[i])) ok = false;
        CHECK(ok, "bind == elementwise XOR");
        // self-inverse: bind(a,a) == 0
        hdc::bind<binary_t, D>(a, a, out);
        bool zero = true; for (int i = 0; i < D; i++) if (out[i] != 0) zero = false;
        CHECK(zero, "bind(a,a) == 0 (self-inverse)");
    }

    std::printf(failures ? "== tb_encoding: %d FAILURE(S) ==\n" : "== tb_encoding: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
}
