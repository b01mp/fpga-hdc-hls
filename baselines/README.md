# CPU/GPU Binary HDC Baseline

This baseline measures the same binary HDC function path used by the baseline
FPGA implementation:

```text
gather -> bind/permute -> bundle -> threshold -> similarity_search
```

It intentionally excludes FPGA-specific placement choices such as BRAM/URAM/HBM
mapping and banking. Those knobs are evaluated on the FPGA side.

## Run

```bash
python -m baselines.hdc_cpu_gpu_baseline --device all --mode all
```

To run the three paper application paths with the current paper-default sizes:

```bash
python -m baselines.hdc_cpu_gpu_baseline \
  --device cpu --mode application --application all --torch-threads 1 \
  --hv-dim 256 --num-features 16 --num-levels 8 --num-classes 10
```

The application defaults are:

| Application | Path | Size |
| --- | --- | --- |
| image classification | gather(feature), gather(value), bind, bundle, threshold, search | D=256, F=16, L=8, K=10 |
| time-series classification | gather(sample), permute(position), bundle, threshold, search | D=128, W=6, V=12, K=4 |
| genome-sequence search | gather(symbol), permute(position), bundle, threshold, search | D=128, W=8, V=4, R=6 |

For small HDC tensors on a large server, pinning PyTorch to one or a few CPU
threads avoids thread-launch overhead dominating the measurement:

```bash
python -m baselines.hdc_cpu_gpu_baseline --device cpu --mode application --torch-threads 1
```

The script writes:

```text
baselines/results/hdc_cpu_gpu_baseline.csv
```

Key columns include latency mean/median/p95, throughput, power, and energy per
operation. GPU power is sampled through optional `pynvml` support. CPU energy is
sampled through Intel RAPL when `/sys/class/powercap/intel-rapl:*` is available.
If neither source is available, the power fields are left blank and
`power_source` is set to `unavailable`.

For time-series and genome rows, `num_features` stores the window size,
`num_levels` stores the symbol vocabulary size, and `num_classes` stores the
number of classes or references.
