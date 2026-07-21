"""PyTorch-style HDC API surface backed by FPGA HLS template metadata.

This package is intentionally small: it records supported HDC API calls as a
typed graph and lowers that graph to a DSE-facing specification. It is not a
general Python compiler or a TorchHD translator.
"""

from .api import (
    bind,
    bundle,
    cast,
    convergence_check,
    flatten,
    gather,
    gemm,
    gen_levels,
    initialize_centroids,
    input_hv,
    input_tensor,
    matvec,
    memory,
    normalize,
    permute,
    place,
    quantize,
    random_hv,
    rematerialize,
    scale,
    similarity_search,
    threshold,
    transpose,
    update,
)
from .graph import Graph, QuantizedRef, TensorRef

__all__ = [
    "Graph",
    "QuantizedRef",
    "TensorRef",
    "bind",
    "bundle",
    "cast",
    "convergence_check",
    "flatten",
    "gather",
    "gemm",
    "gen_levels",
    "initialize_centroids",
    "input_hv",
    "input_tensor",
    "matvec",
    "memory",
    "normalize",
    "permute",
    "place",
    "quantize",
    "random_hv",
    "rematerialize",
    "scale",
    "similarity_search",
    "threshold",
    "transpose",
    "update",
]
