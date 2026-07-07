/**
 * @file tb_memory.cpp
 * @brief C-sim testbench for the Memory category.
 *
 * Tests: gather, place.
 */
#include <cstdio>
#include <ap_int.h>
#include "memory/gather.hpp"
#include "memory/place.hpp"

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("  FAIL: %s\n", msg); failures++; } } while (0)

int main() {
    std::printf("== tb_memory ==\n");

    const int D = 8;
    const int N = 4;

    // ---- gather<int, N=4, D=8> : indexed read --------------------------
    {
        int codebook[N][D] = {{0,1,2,3,4,5,6,7},
                              {10,11,12,13,14,15,16,17},
                              {20,21,22,23,24,25,26,27},
                              {30,31,32,33,34,35,36,37}};
        int out[D];
        hdc::gather<int, N, D>(codebook, 2, out);
        bool ok = true;
        for (int i = 0; i < D; i++) if (out[i] != codebook[2][i]) ok = false;
        CHECK(ok, "gather reads correct row by index");
    }

    // ---- place<int, N=4, D=8> : identity copy (placement seam) --------
    {
        int in[N][D], out[N][D];
        for (int n = 0; n < N; n++)
            for (int i = 0; i < D; i++)
                in[n][i] = n * 10 + i;
        hdc::place<int, N, D>(in, out);
        bool ok = true;
        for (int n = 0; n < N; n++)
            for (int i = 0; i < D; i++)
                if (out[n][i] != in[n][i]) ok = false;
        CHECK(ok, "place is identity (seam for future ARRAY_PARTITION)");
    }

    std::printf(failures ? "== tb_memory: %d FAILURE(S) ==\n" : "== tb_memory: ALL PASS ==\n", failures);
    return failures ? 1 : 0;
}