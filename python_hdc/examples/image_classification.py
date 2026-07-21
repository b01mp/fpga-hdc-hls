"""Image-classification API example used by the paper code listing.

Run:
    python -m python_hdc.examples.image_classification

The printed JSON is the DSE-facing application specification. Numeric kernels
are not executed here; each API call records one supported HDC function node.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import python_hdc as hdc
from python_hdc.lowering import lower_to_dse_spec, write_dse_spec


def build_graph(
    *,
    hv_dim: int = 1024,
    num_features: int = 784,
    num_levels: int = 32,
    num_classes: int = 10,
    dtype: str = "binary",
) -> hdc.Graph:
    graph = hdc.Graph("image_classification")
    with graph.as_default():
        features = hdc.input_tensor("features", shape=(num_features,), dtype="float32")
        item_memory = hdc.memory("item_memory", object_type="codebook", num_vectors=num_features, hv_dim=hv_dim, dtype=dtype)
        level_memory = hdc.memory("level_memory", object_type="codebook", num_vectors=num_levels, hv_dim=hv_dim, dtype=dtype)
        prototypes = hdc.memory("prototypes", object_type="prototype", num_vectors=num_classes, hv_dim=hv_dim, dtype=dtype)

        q = hdc.quantize(features, num_levels=num_levels)
        item_hv = hdc.gather(item_memory, q.feature_indices, hv_dim=hv_dim, role="item_hv")
        level_hv = hdc.gather(level_memory, q.level_indices, hv_dim=hv_dim, role="level_hv")
        encoded = hdc.bind(item_hv, level_hv, hv_dim=hv_dim, dtype=dtype)
        accumulator = hdc.bundle(encoded, hv_dim=hv_dim, num_vectors=num_features)
        query = hdc.threshold(accumulator, hv_dim=hv_dim, dtype=dtype)
        hdc.similarity_search(query, prototypes, num_classes=num_classes, metric="hamming")

    return graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an image-classification HDC graph and lower it to a DSE spec.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    parser.add_argument("--hv-dim", type=int, default=1024)
    parser.add_argument("--num-features", type=int, default=784)
    parser.add_argument("--num-levels", type=int, default=32)
    parser.add_argument("--num-classes", type=int, default=10)
    args = parser.parse_args()

    graph = build_graph(
        hv_dim=args.hv_dim,
        num_features=args.num_features,
        num_levels=args.num_levels,
        num_classes=args.num_classes,
    )

    if args.output:
        spec = write_dse_spec(graph, args.output)
    else:
        spec = lower_to_dse_spec(graph)

    print(json.dumps(spec, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
