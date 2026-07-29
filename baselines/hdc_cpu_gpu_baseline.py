#!/usr/bin/env python3
"""PyTorch CPU/GPU baseline for the binary FPGA HDC function path.

The benchmark mirrors the baseline binary HLS functions:
gather -> bind/permute -> bundle -> threshold -> similarity_search.
FPGA-specific memory-placement knobs such as BRAM/URAM/HBM banking are excluded.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import torch


CSV_FIELDS = [
    "backend",
    "mode",
    "function",
    "application",
    "hv_dim",
    "num_features",
    "num_levels",
    "num_classes",
    "datatype",
    "warmup",
    "repeat",
    "latency_mean_us",
    "latency_median_us",
    "latency_p95_us",
    "throughput_ops_s",
    "power_w",
    "energy_uj",
    "power_source",
    "status",
]


@dataclass(frozen=True)
class BenchmarkInputs:
    feature_codebook: torch.Tensor
    value_codebook: torch.Tensor
    feature_indices: torch.Tensor
    value_indices: torch.Tensor
    prototypes: torch.Tensor


@dataclass(frozen=True)
class OrderedWindowInputs:
    symbol_codebook: torch.Tensor
    symbol_indices: torch.Tensor
    references: torch.Tensor


@dataclass(frozen=True)
class PowerResult:
    power_w: float | None
    energy_uj: float | None
    source: str


def gather(codebook: torch.Tensor, index: torch.Tensor | int) -> torch.Tensor:
    """Indexed codebook lookup, matching include/memory/gather.hpp."""
    return codebook[index]


def bind(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Binary HDC binding: XOR over {0, 1}."""
    return torch.logical_xor(a.bool(), b.bool())


def permute(hv: torch.Tensor, shift: int) -> torch.Tensor:
    """Cyclic rotation matching include/encoding/permute.hpp."""
    if hv.numel() == 0:
        return hv
    return torch.roll(hv, shifts=int(shift) % int(hv.shape[-1]), dims=-1)


def bundle(hvs: torch.Tensor) -> torch.Tensor:
    """Binary HDC bundling: integer accumulation before majority threshold."""
    return hvs.to(torch.int32).sum(dim=0)


def threshold(acc: torch.Tensor, count: int, tie: str = "zero") -> torch.Tensor:
    """Binary majority vote; ties follow the HLS default TIE_SET_ZERO."""
    if tie not in {"zero", "one"}:
        raise ValueError("tie must be 'zero' or 'one'")
    doubled = acc * 2
    if tie == "one":
        return doubled >= count
    return doubled > count


def similarity_search(query: torch.Tensor, prototypes: torch.Tensor) -> torch.Tensor:
    """Binary HDC search: Hamming distance followed by argmin."""
    distances = torch.logical_xor(prototypes.bool(), query.bool()).sum(dim=1)
    return torch.argmin(distances)


def image_classification(inputs: BenchmarkInputs) -> torch.Tensor:
    """Baseline image-classification path used for end-to-end timing."""
    feature_hvs = gather(inputs.feature_codebook, inputs.feature_indices)
    value_hvs = gather(inputs.value_codebook, inputs.value_indices)
    bound = bind(feature_hvs, value_hvs)
    acc = bundle(bound)
    query = threshold(acc, count=int(inputs.feature_indices.numel()))
    return similarity_search(query, inputs.prototypes)


def ordered_window_query(inputs: OrderedWindowInputs) -> torch.Tensor:
    """Shared time-series/genome encoder: gather -> permute -> bundle -> threshold."""
    symbol_hvs = gather(inputs.symbol_codebook, inputs.symbol_indices)
    positional = torch.stack(
        [permute(symbol_hvs[w], shift=w) for w in range(int(inputs.symbol_indices.numel()))],
        dim=0,
    )
    acc = bundle(positional)
    return threshold(acc, count=int(inputs.symbol_indices.numel()))


def time_series_classification(inputs: OrderedWindowInputs) -> torch.Tensor:
    """Time-series path: ordered-window query followed by prototype search."""
    query = ordered_window_query(inputs)
    return similarity_search(query, inputs.references)


def genome_sequence_search(inputs: OrderedWindowInputs) -> torch.Tensor:
    """Genome-search path: ordered-symbol query followed by reference search."""
    query = ordered_window_query(inputs)
    return similarity_search(query, inputs.references)


def make_inputs(
    device: torch.device,
    hv_dim: int,
    num_features: int,
    num_levels: int,
    num_classes: int,
    seed: int,
) -> BenchmarkInputs:
    generator = torch.Generator(device="cpu").manual_seed(seed)
    feature_codebook = torch.randint(
        0, 2, (num_features, hv_dim), generator=generator, dtype=torch.bool
    ).to(device)
    value_codebook = torch.randint(
        0, 2, (num_levels, hv_dim), generator=generator, dtype=torch.bool
    ).to(device)
    prototypes = torch.randint(
        0, 2, (num_classes, hv_dim), generator=generator, dtype=torch.bool
    ).to(device)
    feature_indices = torch.arange(num_features, dtype=torch.long, device=device)
    value_indices = torch.randint(
        0, num_levels, (num_features,), generator=generator, dtype=torch.long
    ).to(device)
    return BenchmarkInputs(
        feature_codebook=feature_codebook,
        value_codebook=value_codebook,
        feature_indices=feature_indices,
        value_indices=value_indices,
        prototypes=prototypes,
    )


def make_ordered_inputs(
    device: torch.device,
    hv_dim: int,
    window_size: int,
    vocab_size: int,
    num_references: int,
    seed: int,
) -> OrderedWindowInputs:
    generator = torch.Generator(device="cpu").manual_seed(seed)
    symbol_codebook = torch.randint(
        0, 2, (vocab_size, hv_dim), generator=generator, dtype=torch.bool
    ).to(device)
    references = torch.randint(
        0, 2, (num_references, hv_dim), generator=generator, dtype=torch.bool
    ).to(device)
    symbol_indices = torch.randint(
        0, vocab_size, (window_size,), generator=generator, dtype=torch.long
    ).to(device)
    return OrderedWindowInputs(
        symbol_codebook=symbol_codebook,
        symbol_indices=symbol_indices,
        references=references,
    )


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


class EnergyMeter:
    """Best-effort energy/power measurement for CPU RAPL or NVIDIA NVML."""

    def __init__(self, device: torch.device, poll_interval_s: float = 0.01):
        self.device = device
        self.poll_interval_s = poll_interval_s
        self._source = "unavailable"
        self._start_energy_uj: int | None = None
        self._start_energy_mj: int | None = None
        self._start_time = 0.0
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._power_samples_w: list[float] = []
        self._nvml = None
        self._nvml_handle = None
        self._rapl_path = self._find_rapl_energy_path() if device.type == "cpu" else None

        if device.type == "cuda":
            self._init_nvml()

    def __enter__(self) -> "EnergyMeter":
        self._start_time = time.perf_counter()
        if self.device.type == "cpu" and self._rapl_path:
            self._source = "rapl"
            self._start_energy_uj = self._read_int(self._rapl_path)
        elif self.device.type == "cuda" and self._nvml_handle is not None:
            self._source = "nvml"
            self._start_energy_mj = self._read_nvml_energy_mj()
            if self._start_energy_mj is None:
                self._start_power_polling()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        synchronize(self.device)
        elapsed_s = max(time.perf_counter() - self._start_time, 1e-12)
        self.result = self._finish(elapsed_s)

    def _finish(self, elapsed_s: float) -> PowerResult:
        if self.device.type == "cpu" and self._rapl_path and self._start_energy_uj is not None:
            end_energy = self._read_int(self._rapl_path)
            if end_energy is not None:
                energy_uj = float(max(end_energy - self._start_energy_uj, 0))
                return PowerResult(power_w=energy_uj / elapsed_s / 1_000_000.0,
                                   energy_uj=energy_uj,
                                   source="rapl")

        if self.device.type == "cuda" and self._nvml_handle is not None:
            end_energy_mj = self._read_nvml_energy_mj()
            if self._start_energy_mj is not None and end_energy_mj is not None:
                energy_uj = float(max(end_energy_mj - self._start_energy_mj, 0) * 1000)
                return PowerResult(power_w=energy_uj / elapsed_s / 1_000_000.0,
                                   energy_uj=energy_uj,
                                   source="nvml_total_energy")

            self._stop_power_polling()
            if self._power_samples_w:
                avg_power = statistics.fmean(self._power_samples_w)
                return PowerResult(power_w=avg_power,
                                   energy_uj=avg_power * elapsed_s * 1_000_000.0,
                                   source="nvml_power_polling")

        return PowerResult(power_w=None, energy_uj=None, source="unavailable")

    @staticmethod
    def _find_rapl_energy_path() -> Path | None:
        root = Path("/sys/class/powercap")
        if not root.exists():
            return None
        for path in sorted(root.glob("intel-rapl:*/energy_uj")):
            if path.is_file():
                return path
        return None

    @staticmethod
    def _read_int(path: Path) -> int | None:
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            return None

    def _init_nvml(self) -> None:
        try:
            import pynvml  # type: ignore

            pynvml.nvmlInit()
            index = self.device.index if self.device.index is not None else torch.cuda.current_device()
            self._nvml = pynvml
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        except Exception:
            self._nvml = None
            self._nvml_handle = None

    def _read_nvml_energy_mj(self) -> int | None:
        if self._nvml is None or self._nvml_handle is None:
            return None
        try:
            return int(self._nvml.nvmlDeviceGetTotalEnergyConsumption(self._nvml_handle))
        except Exception:
            return None

    def _read_nvml_power_w(self) -> float | None:
        if self._nvml is None or self._nvml_handle is None:
            return None
        try:
            return float(self._nvml.nvmlDeviceGetPowerUsage(self._nvml_handle)) / 1000.0
        except Exception:
            return None

    def _start_power_polling(self) -> None:
        self._stop_event = threading.Event()

        def poll() -> None:
            while self._stop_event is not None and not self._stop_event.is_set():
                power = self._read_nvml_power_w()
                if power is not None:
                    self._power_samples_w.append(power)
                time.sleep(self.poll_interval_s)

        self._thread = threading.Thread(target=poll, daemon=True)
        self._thread.start()

    def _stop_power_polling(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def measure_latency_us(
    fn: Callable[[], torch.Tensor],
    device: torch.device,
    warmup: int,
    repeat: int,
) -> tuple[list[float], PowerResult]:
    for _ in range(warmup):
        fn()
    synchronize(device)

    latencies: list[float] = []
    with EnergyMeter(device) as meter:
        if device.type == "cuda":
            starter = torch.cuda.Event(enable_timing=True)
            ender = torch.cuda.Event(enable_timing=True)
            for _ in range(repeat):
                starter.record()
                fn()
                ender.record()
                torch.cuda.synchronize(device)
                latencies.append(float(starter.elapsed_time(ender)) * 1000.0)
        else:
            for _ in range(repeat):
                start = time.perf_counter()
                fn()
                latencies.append((time.perf_counter() - start) * 1_000_000.0)
    return latencies, meter.result


def summarize_latencies(latencies_us: list[float]) -> tuple[float, float, float]:
    if not latencies_us:
        raise ValueError("latencies_us must be non-empty")
    sorted_latencies = sorted(latencies_us)
    p95_idx = min(len(sorted_latencies) - 1, math.ceil(0.95 * len(sorted_latencies)) - 1)
    return (
        statistics.fmean(latencies_us),
        statistics.median(latencies_us),
        sorted_latencies[p95_idx],
    )


def make_row(
    *,
    device: torch.device,
    mode: str,
    function: str,
    application: str,
    hv_dim: int,
    num_features: int,
    num_levels: int,
    num_classes: int,
    warmup: int,
    repeat: int,
    latencies_us: list[float],
    power: PowerResult,
) -> dict[str, str]:
    mean_us, median_us, p95_us = summarize_latencies(latencies_us)
    throughput = 1_000_000.0 / mean_us if mean_us > 0 else 0.0
    energy_per_op_uj = power.energy_uj / repeat if power.energy_uj is not None else None
    return {
        "backend": str(device),
        "mode": mode,
        "function": function,
        "application": application,
        "hv_dim": str(hv_dim),
        "num_features": str(num_features),
        "num_levels": str(num_levels),
        "num_classes": str(num_classes),
        "datatype": "binary",
        "warmup": str(warmup),
        "repeat": str(repeat),
        "latency_mean_us": f"{mean_us:.6f}",
        "latency_median_us": f"{median_us:.6f}",
        "latency_p95_us": f"{p95_us:.6f}",
        "throughput_ops_s": f"{throughput:.6f}",
        "power_w": "" if power.power_w is None else f"{power.power_w:.6f}",
        "energy_uj": "" if energy_per_op_uj is None else f"{energy_per_op_uj:.6f}",
        "power_source": power.source,
        "status": "ok",
    }


def primitive_workloads(inputs: BenchmarkInputs) -> Iterable[tuple[str, Callable[[], torch.Tensor]]]:
    yield "gather", lambda: gather(inputs.feature_codebook, inputs.feature_indices[0])
    yield "bind", lambda: bind(inputs.feature_codebook[0], inputs.value_codebook[0])
    yield "permute", lambda: permute(inputs.feature_codebook[0], shift=1)
    yield "bundle", lambda: bundle(inputs.feature_codebook)
    yield "threshold", lambda: threshold(bundle(inputs.feature_codebook), count=inputs.feature_indices.numel())
    query = threshold(bundle(inputs.feature_codebook), count=inputs.feature_indices.numel())
    yield "similarity_search", lambda: similarity_search(query, inputs.prototypes)


def application_workloads(
    device: torch.device,
    application: str,
    seed: int,
    hv_dim: int,
    num_features: int,
    num_levels: int,
    num_classes: int,
) -> Iterable[tuple[str, int, int, int, int, Callable[[], torch.Tensor]]]:
    if application in {"image", "image_classification", "all"}:
        image_inputs = make_inputs(device, hv_dim, num_features, num_levels, num_classes, seed)
        yield (
            "image_classification",
            hv_dim,
            num_features,
            num_levels,
            num_classes,
            lambda: image_classification(image_inputs),
        )

    if application in {"time_series", "time_series_classification", "all"}:
        ts_hv_dim, ts_window, ts_vocab, ts_classes = 128, 6, 12, 4
        ts_inputs = make_ordered_inputs(
            device, ts_hv_dim, ts_window, ts_vocab, ts_classes, seed + 101
        )
        yield (
            "time_series_classification",
            ts_hv_dim,
            ts_window,
            ts_vocab,
            ts_classes,
            lambda: time_series_classification(ts_inputs),
        )

    if application in {"genome", "genome_sequence_search", "all"}:
        gen_hv_dim, gen_window, gen_vocab, gen_refs = 128, 8, 4, 6
        gen_inputs = make_ordered_inputs(
            device, gen_hv_dim, gen_window, gen_vocab, gen_refs, seed + 202
        )
        yield (
            "genome_sequence_search",
            gen_hv_dim,
            gen_window,
            gen_vocab,
            gen_refs,
            lambda: genome_sequence_search(gen_inputs),
        )


def run_suite(
    *,
    devices: list[torch.device],
    mode: str,
    application: str,
    hv_dim: int,
    num_features: int,
    num_levels: int,
    num_classes: int,
    warmup: int,
    repeat: int,
    seed: int,
    output: Path,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for device in devices:
        inputs = make_inputs(device, hv_dim, num_features, num_levels, num_classes, seed)
        if mode in {"primitive", "all"}:
            for name, workload in primitive_workloads(inputs):
                latencies, power = measure_latency_us(workload, device, warmup, repeat)
                rows.append(make_row(
                    device=device,
                    mode="primitive",
                    function=name,
                    application="",
                    hv_dim=hv_dim,
                    num_features=num_features,
                    num_levels=num_levels,
                    num_classes=num_classes,
                    warmup=warmup,
                    repeat=repeat,
                    latencies_us=latencies,
                    power=power,
                ))
        if mode in {"application", "all"}:
            for app_name, app_d, app_features, app_levels, app_classes, workload in application_workloads(
                device=device,
                application=application,
                seed=seed,
                hv_dim=hv_dim,
                num_features=num_features,
                num_levels=num_levels,
                num_classes=num_classes,
            ):
                latencies, power = measure_latency_us(workload, device, warmup, repeat)
                rows.append(make_row(
                    device=device,
                    mode="application",
                    function="",
                    application=app_name,
                    hv_dim=app_d,
                    num_features=app_features,
                    num_levels=app_levels,
                    num_classes=app_classes,
                    warmup=warmup,
                    repeat=repeat,
                    latencies_us=latencies,
                    power=power,
                ))

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def parse_devices(value: str) -> list[torch.device]:
    if value == "all":
        devices = [torch.device("cpu")]
        if torch.cuda.is_available():
            devices.append(torch.device("cuda"))
        return devices
    if value == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
    return [torch.device(value)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=["cpu", "cuda", "all"], default="all")
    parser.add_argument("--mode", choices=["primitive", "application", "all"], default="all")
    parser.add_argument(
        "--application",
        choices=[
            "image",
            "image_classification",
            "time_series",
            "time_series_classification",
            "genome",
            "genome_sequence_search",
            "all",
        ],
        default="image",
        help="Application path to benchmark in application mode.",
    )
    parser.add_argument("--hv-dim", type=int, default=256)
    parser.add_argument("--num-features", type=int, default=128)
    parser.add_argument("--num-levels", type=int, default=16)
    parser.add_argument("--num-classes", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=100)
    parser.add_argument(
        "--torch-threads",
        type=int,
        default=None,
        help="Set torch CPU intra-op and inter-op thread counts for stable CPU latency.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("baselines/results/hdc_cpu_gpu_baseline.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.torch_threads is not None:
        torch.set_num_threads(args.torch_threads)
        torch.set_num_interop_threads(args.torch_threads)
    rows = run_suite(
        devices=parse_devices(args.device),
        mode=args.mode,
        application=args.application,
        hv_dim=args.hv_dim,
        num_features=args.num_features,
        num_levels=args.num_levels,
        num_classes=args.num_classes,
        warmup=args.warmup,
        repeat=args.repeat,
        seed=args.seed,
        output=args.output,
    )
    print(f"wrote {args.output} ({len(rows)} rows)")
    for row in rows:
        name = row["function"] or row["application"]
        print(
            f"{row['backend']:<8} {row['mode']:<11} {name:<20} "
            f"mean={row['latency_mean_us']} us p95={row['latency_p95_us']} us "
            f"power={row['power_w'] or 'NA'} W source={row['power_source']}"
        )


if __name__ == "__main__":
    main()
