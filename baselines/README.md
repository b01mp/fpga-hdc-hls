# CPU/GPU Binary HDC Baseline

This baseline measures the same binary HDC function path used by the baseline
FPGA implementation:

```text
gather -> bind -> bundle -> threshold -> similarity_search
```

It intentionally excludes FPGA-specific placement choices such as BRAM/URAM/HBM
mapping and banking. Those knobs are evaluated on the FPGA side.

## Run

```bash
python -m baselines.hdc_cpu_gpu_baseline --device all --mode all
```

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
