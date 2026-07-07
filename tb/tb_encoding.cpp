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
#include "encoding/permute.hpp"
#include "encoding/scale.hpp"
#include "encoding/gemm.hpp"
#include "encoding/matvec.hpp"
#include "encoding/transpose.hpp"
#include "encoding/flatten.hpp"

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
         // ---- permute<int, D=8> : cyclic rotate, invertible -----------------
    {
        const int D = 8;
        int in[D], out[D], back[D];
        for (int i = 0; i < D; i++) in[i] = i;          // 0..7
        hdc::permute<int, D>(in, 3, out);               // rotate by +3
        CHECK(out[3] == in[0], "permute places in[0] at index +shift");
        hdc::permute<int, D>(out, -3, back);            // rotate back by -3
        bool rt = true;
        for (int i = 0; i < D; i++) if (back[i] != in[i]) rt = false;
        CHECK(rt, "permute(+s) then permute(-s) round-trips");
    }

    // ---- scale<int, int, D=4> : elementwise weight ---------------------
    {
        const int D = 4;
        int in[D] = {1,2,3,4}, out[D];
        hdc::scale<int, int, D>(in, 3, out);            // multiply each by 3
        int exp[D] = {3,6,9,12};
        bool ok = true;
        for (int i = 0; i < D; i++) if (out[i] != exp[i]) ok = false;
        CHECK(ok, "scale multiplies each element by w");
    }

    // ---- gemm<int,int, 2,2,2> : dense matmul ---------------------------
    {
        int A[2][2] = {{1,2},{3,4}};
        int B[2][2] = {{5,6},{7,8}};
        int C[2][2];
        hdc::gemm<int, int, 2, 2, 2>(A, B, C);          // C = A*B = [[19,22],[43,50]]
        bool ok = (C[0][0]==19 && C[0][1]==22 && C[1][0]==43 && C[1][1]==50);
        CHECK(ok, "gemm 2x2 matmul golden");
    }

    // ---- matvec<int,int, 2,3> : matrix-vector --------------------------
    {
        int A[2][3] = {{1,2,3},{4,5,6}};
        int x[3] = {1,0,-1};
        int y[2];
        hdc::matvec<int, int, 2, 3>(A, x, y);           // y = A*x = [-2,-2]
        CHECK(y[0]==-2 && y[1]==-2, "matvec golden (y = A*x)");
    }

    // ---- transpose<int, 2,3> ------------------------------------------
    {
        int in[2][3] = {{1,2,3},{4,5,6}};
        int out[3][2];
        hdc::transpose<int, 2, 3>(in, out);
        bool ok = true;
        for (int r = 0; r < 2; r++)
            for (int c = 0; c < 3; c++)
                if (out[c][r] != in[r][c]) ok = false;
        CHECK(ok, "transpose swaps axes");
    }

    // ---- flatten<int, 2,3> --------------------------------------------
    {
        int in[2][3] = {{1,2,3},{4,5,6}};
        int out[6];
        hdc::flatten<int, 2, 3>(in, out);               // row-major -> 1,2,3,4,5,6
        int exp[6] = {1,2,3,4,5,6};
        bool ok = true;
        for (int i = 0; i < 6; i++) if (out[i] != exp[i]) ok = false;
        CHECK(ok, "flatten row-major");
    }

    // ==== Novelty 1: datatype-parametric bind (one primitive, tag-selected op) ====

    // ---- bind<bipolar> : multiply over {-1,+1} ------------------------
    {
        const int D = 8;
        hdc::bipolar_t a[D], b[D], out[D];
        for (int i = 0; i < D; i++) { a[i] = (i & 1) ? 1 : -1; b[i] = (i & 2) ? 1 : -1; }
        hdc::bind<hdc::bipolar_t, D, hdc::bipolar_tag>(a, b, out);
        bool ok = true;
        for (int i = 0; i < D; i++) if (out[i] != (hdc::bipolar_t)(a[i] * b[i])) ok = false;
        CHECK(ok, "bind<bipolar> == elementwise multiply");
        hdc::bind<hdc::bipolar_t, D, hdc::bipolar_tag>(a, a, out);      // self-inverse: x*x = +1
        bool ones = true; for (int i = 0; i < D; i++) if (out[i] != 1) ones = false;
        CHECK(ones, "bind<bipolar>(a,a) == +1 (self-inverse)");
    }

    // ---- bind<integer> : multiply (ap_int<8>) -------------------------
    {
        const int D = 4;
        typedef ap_int<8> int8;
        int8 a[D] = {2, -3, 4, -1}, b[D] = {3, 3, -2, -5}, out[D];
        hdc::bind<int8, D, hdc::integer_tag>(a, b, out);
        int exp[D] = {6, -9, -8, 5};
        bool ok = true;
        for (int i = 0; i < D; i++) if (out[i] != (int8)exp[i]) ok = false;
        CHECK(ok, "bind<integer> == elementwise multiply");
    }

    // ---- bind<fixed> : multiply (ap_fixed<16,8>) ----------------------
    {
        const int D = 4;
        typedef ap_fixed<16,8> fx;
        fx a[D] = {1.0, -1.0, 2.0, 0.5}, b[D] = {2.0, 2.0, 1.0, 4.0}, out[D];
        hdc::bind<fx, D, hdc::fixed_tag>(a, b, out);                    // {2,-2,2,2}
        bool ok = true;
        for (int i = 0; i < D; i++) if (out[i] != (fx)(a[i] * b[i])) ok = false;
        CHECK(ok, "bind<fixed> == elementwise multiply");
    }

    // ---- bind<pow2> : add exponents, since 2^a * 2^b = 2^(a+b) --------
    {
        const int D = 4;
        typedef ap_uint<5> ex;                                         // stores exponent k
        ex a[D] = {1, 2, 3, 0}, b[D] = {0, 1, 2, 4}, out[D];
        hdc::bind<ex, D, hdc::pow2_tag>(a, b, out);                     // {1,3,5,4}
        int exp[D] = {1, 3, 5, 4};
        bool ok = true;
        for (int i = 0; i < D; i++) if (out[i] != (ex)exp[i]) ok = false;
        CHECK(ok, "bind<pow2> == exponent addition (shift)");
    }

    std::printf(failures ? "== tb_encoding: %d FAILURE(S) ==\n" : "== tb_encoding: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
    
}
