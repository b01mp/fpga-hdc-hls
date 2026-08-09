/**
 * hdc_mem_host.cpp -- XRT host for the off-chip memory study on the U280.
 *
 * Measures, on real hardware, for one (design, CP) build:
 *
 *     latency      wall-clock kernel execution time, median of N runs
 *     bandwidth    bytes that actually crossed the HBM interface / time
 *     throughput   prototypes (hypervectors) consumed per second
 *
 * Hardware utilisation is not measurable from here -- it comes from the
 * post-route report of the same build, joined later by DSE/collect_device.py.
 *
 * WHY K AND DATATYPE ARE RUNTIME AND CP IS NOT
 *     The gather datapath moves packed 512-bit words and never interprets an
 *     element, so bits-per-element changes only how many bytes a prototype
 *     occupies -- not the hardware. Class count changes only how many words
 *     must be read. Both are therefore swept here, at runtime, in
 *     milliseconds. Channel count changes the number of m_axi ports, which is
 *     structural, so each CP needs its own xclbin.
 *
 * Usage:
 *   ./hdc_mem_host --xclbin build/stream_cp8.xclbin --kernel krnl_hdc_stream \
 *                  --cp 8 --design stream --out results/stream_cp8.csv
 *
 * There are two Alveo cards in this machine (a U200 and a U280). The BDF
 * defaults to the U280; pass --bdf to override. Selecting by index would be a
 * coin flip.
 */
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#include <fstream>

#include "xrt/xrt_device.h"
#include "xrt/xrt_kernel.h"
#include "xrt/xrt_bo.h"

// ---------------------------------------------------------------- constants
static const int      D_ELEMS  = 10240;   // hypervector dimension, elements
static const int      WBYTES   = 64;      // 512-bit AXI word
static const int      TILE     = 64;      // words per burst tile (must match kernel)
static const double   FCLK_HZ  = 300e6;   // for the cycle column

// Per-datatype class-count grids. Chosen so the top point of every grid moves
// the same number of bytes (~168 MB), and so each grid straddles the on-chip
// ceiling established by the capacity crossover: at D=10240, U280 BRAM holds
// about 7,400 binary / 930 int8 / 232 int32 prototypes, and BRAM+URAM about
// 35,000 / 4,400 / 1,100. Points below the ceiling could have stayed on chip;
// points above it had no choice but HBM. That contrast is the figure.
struct Grid { int bits; std::vector<int> K; };
static std::vector<Grid> full_grids() {
    return {
        {1,  {1024, 4096, 16384, 65536, 131072}},
        {8,  { 128,  512,  2048,  8192,  16384}},
        {32, {  32,  128,   512,  2048,   4096}},
    };
}
// Emulation moves a few KB, not a few hundred MB. hw_emu of the real grid
// would run for days; these points exist only to prove correctness.
static std::vector<Grid> emu_grids() {
    return {{1, {64}}, {8, {16}}, {32, {8}}};
}

// --------------------------------------------------------------- helpers
// Hardware emulation runs the whole platform -- PCIe, DMA, HBM controllers --
// in cycle-accurate RTL, so every byte transferred costs simulated cycles. A
// few hundred KB takes hours. Emulation exists here only to prove the kernel
// does not deadlock and returns correct data, so the transfer is clamped to a
// couple of tiles. The performance columns from an emulation run are
// meaningless by construction and must never be quoted.
static const long long EMU_MAX_WORDS = 128;

static long long words_per_channel(int K, int CP, int bits) {
    // bytes per prototype = D * bits / 8 ; words per prototype = that / 64
    long long wpp = (long long)D_ELEMS * bits / 8 / WBYTES;   // 20 * bits
    long long raw = (long long)(K / CP) * wpp;
    if (raw < TILE) raw = TILE;
    // the buffered kernel consumes whole tiles, so round up and report the
    // padded byte count -- bandwidth is quoted on bytes that really moved
    return ((raw + TILE - 1) / TILE) * TILE;
}

static uint64_t fold_word(const uint64_t *w) {   // 8 x 64-bit lanes -> 1
    uint64_t f = 0;
    for (int i = 0; i < 8; i++) f ^= w[i];
    return f;
}

static std::string arg_of(int argc, char **argv, const char *flag,
                          const std::string &dflt) {
    for (int i = 1; i + 1 < argc; i++)
        if (!strcmp(argv[i], flag)) return std::string(argv[i + 1]);
    return dflt;
}

// ------------------------------------------------------------------- main
int main(int argc, char **argv) {
    const std::string xclbin = arg_of(argc, argv, "--xclbin", "");
    const std::string kname  = arg_of(argc, argv, "--kernel", "");
    const std::string design = arg_of(argc, argv, "--design", "unknown");
    const std::string outcsv = arg_of(argc, argv, "--out", "device_results.csv");
    const std::string bdf    = arg_of(argc, argv, "--bdf", "0000:3b:00.1");
    const int CP    = std::stoi(arg_of(argc, argv, "--cp", "8"));
    int       iters = std::stoi(arg_of(argc, argv, "--iters", "10"));

    if (xclbin.empty() || kname.empty()) {
        fprintf(stderr, "usage: %s --xclbin <f> --kernel <k> --cp <n> "
                        "[--design tag] [--out csv] [--bdf B] [--iters N]\n", argv[0]);
        return 2;
    }

    const char *emu = getenv("XCL_EMULATION_MODE");
    const bool  is_emu = (emu != nullptr);
    if (is_emu) { iters = 1; printf("[emulation mode: %s -- tiny grid]\n", emu); }
    auto grids = is_emu ? emu_grids() : full_grids();

    // In emulation there is no physical card: XRT presents one virtual device
    // at index 0, described by emconfig.json, and a BDF string does not
    // resolve. On hardware the index is a coin flip between the U200 and the
    // U280 in this machine, so there the BDF is the only safe selector.
    auto open_device = [&]() {
        if (is_emu) {
            printf("device (emulated, index 0)\n");
            return xrt::device(static_cast<unsigned int>(0));
        }
        printf("device %s\n", bdf.c_str());
        return xrt::device(bdf);
    };

    printf("xclbin %s\nkernel %s  CP=%d  design=%s\n",
           xclbin.c_str(), kname.c_str(), CP, design.c_str());

    auto device = open_device();
    auto uuid   = device.load_xclbin(xclbin);
    auto krnl   = xrt::kernel(device, uuid, kname);

    // ---- allocate once at the largest size any point needs, reuse after ----
    long long max_words = 0;
    for (auto &g : grids)
        for (int K : g.K)
            max_words = std::max(max_words, words_per_channel(K, CP, g.bits));
    if (is_emu) max_words = std::min(max_words, EMU_MAX_WORDS);
    const size_t max_bytes = (size_t)max_words * WBYTES;
    printf("allocating %d x %.1f MB on HBM\n", CP, max_bytes / 1048576.0);

    std::vector<xrt::bo> banks;
    std::vector<uint64_t *> hostp;
    for (int i = 0; i < CP; i++) {
        banks.emplace_back(device, max_bytes, krnl.group_id(i));
        hostp.push_back(banks[i].map<uint64_t *>());
    }
    auto obo  = xrt::bo(device, (size_t)CP * sizeof(uint64_t), krnl.group_id(CP));
    auto ohost = obo.map<uint64_t *>();

    // deterministic fill; a constant pattern would let the memory system look
    // better than it is and would make the checksum useless as a check
    const size_t lanes = max_bytes / sizeof(uint64_t);
    for (int i = 0; i < CP; i++) {
        uint64_t s = 0x9E3779B97F4A7C15ULL * (uint64_t)(i + 1);
        for (size_t j = 0; j < lanes; j++) {
            s ^= s << 13; s ^= s >> 7; s ^= s << 17;
            hostp[i][j] = s;
        }
        banks[i].sync(XCL_BO_SYNC_BO_TO_DEVICE);
    }
    printf("buffers resident on device\n\n");

    std::ofstream csv(outcsv);
    csv << "design,CP,bits,K,D,words_per_channel,bytes_moved,bytes_logical,"
           "latency_us_median,latency_us_min,cycles_median,bw_GBps,"
           "throughput_Mhv_per_s,checksum_ok\n";

    printf("%-8s %5s %8s %10s %12s %12s %10s %8s\n",
           "design", "bits", "K", "MB moved", "lat us (med)", "BW GB/s",
           "Mhv/s", "check");
    printf("%s\n", std::string(84, '-').c_str());

    for (auto &g : grids) {
        for (int K : g.K) {
            long long nw = words_per_channel(K, CP, g.bits);
            if (is_emu) nw = std::min(nw, EMU_MAX_WORDS);
            const uint64_t  moved = (uint64_t)nw * WBYTES * CP;
            const uint64_t  logic = (uint64_t)K * D_ELEMS * g.bits / 8;

            auto run = xrt::run(krnl);
            for (int i = 0; i < CP; i++) run.set_arg(i, banks[i]);
            run.set_arg(CP, obo);
            run.set_arg(CP + 1, (int)nw);

            for (int w = 0; w < (is_emu ? 0 : 3); w++) { run.start(); run.wait(); }

            std::vector<double> us;
            for (int it = 0; it < iters; it++) {
                auto t0 = std::chrono::steady_clock::now();
                run.start();
                run.wait();
                auto t1 = std::chrono::steady_clock::now();
                us.push_back(std::chrono::duration<double, std::micro>(t1 - t0).count());
            }
            std::sort(us.begin(), us.end());
            const double med = us[us.size() / 2];
            const double mn  = us.front();

            // verify the transfer really happened
            obo.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
            bool ok = true;
            for (int i = 0; i < CP && ok; i++) {
                uint64_t exp = 0;
                for (long long w = 0; w < nw; w++)
                    exp ^= fold_word(&hostp[i][w * 8]);
                if (ohost[i] != exp) {
                    ok = false;
                    fprintf(stderr, "  CHECKSUM MISMATCH ch%d: got %016llx want %016llx\n",
                            i, (unsigned long long)ohost[i], (unsigned long long)exp);
                }
            }

            const double sec  = med / 1e6;
            const double bw   = moved / sec / 1e9;
            const double thr  = K / sec / 1e6;
            const double cyc  = sec * FCLK_HZ;

            printf("%-8s %5d %8d %10.2f %12.1f %12.2f %10.3f %8s\n",
                   design.c_str(), g.bits, K, moved / 1048576.0, med, bw, thr,
                   ok ? "ok" : "FAIL");

            csv << design << "," << CP << "," << g.bits << "," << K << ","
                << D_ELEMS << "," << nw << "," << moved << "," << logic << ","
                << med << "," << mn << "," << (long long)cyc << "," << bw << ","
                << thr << "," << (ok ? 1 : 0) << "\n";
        }
    }
    csv.close();
    printf("\nwrote %s\n", outcsv.c_str());
    return 0;
}
