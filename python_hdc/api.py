from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

from .graph import QuantizedRef, TensorRef, active_graph


def input_tensor(name: str, *, shape: Sequence[int], dtype: str = "float32", role: str = "input") -> TensorRef:
    return active_graph().add_input(name, shape=shape, dtype=dtype, role=role)


def input_hv(name: str, *, hv_dim: int, dtype: str = "binary", role: str = "hypervector") -> TensorRef:
    return active_graph().add_input(name, shape=(hv_dim,), dtype=dtype, hv_dim=hv_dim, role=role)


def memory(
    name: str,
    *,
    object_type: str,
    num_vectors: int,
    hv_dim: int,
    dtype: str = "binary",
    role: str = "memory",
) -> TensorRef:
    return active_graph().add_input(
        name,
        shape=(num_vectors, hv_dim),
        dtype=dtype,
        hv_dim=hv_dim,
        role=role,
        object_type=object_type,
    )


def _single(
    op: str,
    inputs: Iterable[TensorRef],
    *,
    hv_dim: Optional[int] = None,
    shape: Optional[Sequence[int]] = None,
    dtype: str = "binary",
    role: str = "hypervector",
    edge_policy: str = "local_buffer",
    **params,
) -> TensorRef:
    params = {k: v for k, v in params.items() if v is not None}
    if hv_dim is not None:
        params.setdefault("hv_dim", hv_dim)
    output_shape = tuple(shape) if shape is not None else ((hv_dim,) if hv_dim else ())
    outputs = [{"dtype": dtype, "hv_dim": hv_dim, "role": role, "shape": output_shape}]
    return active_graph().add_node(op, list(inputs), params=params, outputs=outputs, edge_policy=edge_policy)[0]


def quantize(x: TensorRef, *, num_levels: int, feature_parallelism: Optional[int] = None) -> QuantizedRef:
    params = {"num_levels": num_levels}
    if feature_parallelism is not None:
        params["feature_parallelism"] = feature_parallelism
    feature_idx, level_idx = active_graph().add_node(
        "quantize",
        [x],
        params=params,
        outputs=[
            {"dtype": "int32", "role": "feature_indices", "shape": x.shape, "name": f"{x.name}_feature_idx"},
            {"dtype": "int32", "role": "level_indices", "shape": x.shape, "name": f"{x.name}_level_idx"},
        ],
    )
    return QuantizedRef(feature_indices=feature_idx, level_indices=level_idx)


def gather(
    memory_obj: TensorRef,
    indices: TensorRef,
    *,
    hv_dim: int,
    role: str = "hypervector",
    dtype: Optional[str] = None,
    memory_space: Optional[str] = None,
    banking_factor: Optional[int] = None,
    storage_mode: Optional[str] = None,
) -> TensorRef:
    return _single(
        "gather",
        [memory_obj, indices],
        hv_dim=hv_dim,
        dtype=dtype or memory_obj.dtype,
        role=role,
        memory_space=memory_space,
        banking_factor=banking_factor,
        storage_mode=storage_mode,
    )


def bind(a: TensorRef, b: TensorRef, *, hv_dim: Optional[int] = None, dtype: Optional[str] = None) -> TensorRef:
    return _single("bind", [a, b], hv_dim=hv_dim or a.hv_dim or b.hv_dim, dtype=dtype or a.dtype)


def bundle(
    vectors: TensorRef | Sequence[TensorRef],
    *,
    hv_dim: Optional[int] = None,
    num_vectors: Optional[int] = None,
    accumulator_bitwidth: Optional[int] = None,
) -> TensorRef:
    inputs = list(vectors) if isinstance(vectors, (list, tuple)) else [vectors]
    inferred_dim = hv_dim or inputs[0].hv_dim
    return _single(
        "bundle",
        inputs,
        hv_dim=inferred_dim,
        dtype="int32",
        role="accumulator",
        num_vectors=num_vectors or len(inputs),
        accumulator_bitwidth=accumulator_bitwidth,
    )


def threshold(
    accumulator: TensorRef,
    *,
    hv_dim: Optional[int] = None,
    dtype: str = "binary",
    accumulator_bitwidth: Optional[int] = None,
) -> TensorRef:
    return _single(
        "threshold",
        [accumulator],
        hv_dim=hv_dim or accumulator.hv_dim,
        dtype=dtype,
        accumulator_bitwidth=accumulator_bitwidth,
    )


def similarity_search(
    query: TensorRef,
    prototypes: TensorRef,
    *,
    num_classes: int,
    metric: str = "hamming",
    class_parallelism: Optional[int] = None,
) -> TensorRef:
    return _single(
        "similarity_search",
        [query, prototypes],
        hv_dim=None,
        dtype="int32",
        role="class_id",
        num_classes=num_classes,
        metric=metric,
        similarity_metric=metric,
        class_parallelism=class_parallelism,
    )


def random_hv(*, name: str = "random_hv", hv_dim: int, dtype: str = "binary", seed: Optional[int] = None) -> TensorRef:
    return _single("random_hv", [], hv_dim=hv_dim, dtype=dtype, seed=seed, role=name)


def gen_levels(*, num_levels: int, hv_dim: int, dtype: str = "binary", level_mode: str = "linear") -> TensorRef:
    return _single("gen_levels", [], hv_dim=hv_dim, dtype=dtype, role="level_codebook", num_levels=num_levels, level_mode=level_mode)


def rematerialize(seed: TensorRef, *, hv_dim: int, dtype: str = "binary", seed_mode: str = "counter") -> TensorRef:
    return _single("rematerialize", [seed], hv_dim=hv_dim, dtype=dtype, seed_mode=seed_mode)


def permute(x: TensorRef, *, shift: int = 1, hv_dim: Optional[int] = None) -> TensorRef:
    return _single("permute", [x], hv_dim=hv_dim or x.hv_dim, dtype=x.dtype, shift=shift)


def scale(x: TensorRef, factor: TensorRef | float, *, hv_dim: Optional[int] = None) -> TensorRef:
    inputs = [x] if isinstance(factor, (int, float)) else [x, factor]
    factor_value = factor if isinstance(factor, (int, float)) else None
    return _single("scale", inputs, hv_dim=hv_dim or x.hv_dim, dtype=x.dtype, factor=factor_value)


def gemm(a: TensorRef, b: TensorRef, *, rows: int, cols: int, inner_dim: int, dtype: str = "fixed") -> TensorRef:
    return _single("gemm", [a, b], dtype=dtype, role="matrix", shape=(rows, cols), rows=rows, cols=cols, inner_dim=inner_dim)


def matvec(a: TensorRef, x: TensorRef, *, rows: int, cols: int, dtype: str = "fixed") -> TensorRef:
    return _single("matvec", [a, x], dtype=dtype, role="vector", shape=(rows,), rows=rows, cols=cols)


def transpose(x: TensorRef, *, rows: int, cols: int) -> TensorRef:
    return _single("transpose", [x], dtype=x.dtype, role=x.role, shape=(cols, rows), rows=rows, cols=cols)


def flatten(x: TensorRef, *, input_shape: Tuple[int, ...]) -> TensorRef:
    size = 1
    for dim in input_shape:
        size *= dim
    return _single("flatten", [x], dtype=x.dtype, role="vector", shape=(size,), input_shape=input_shape)


def normalize(x: TensorRef, *, hv_dim: Optional[int] = None, mode: str = "l2") -> TensorRef:
    return _single("normalize", [x], hv_dim=hv_dim or x.hv_dim, dtype=x.dtype, normalization_mode=mode)


def update(prototype: TensorRef, sample: TensorRef, *, mode: str = "add", learning_rate: Optional[float] = None) -> TensorRef:
    return _single(
        "update",
        [prototype, sample],
        hv_dim=prototype.hv_dim or sample.hv_dim,
        dtype=prototype.dtype,
        update_mode=mode,
        learning_rate=learning_rate,
    )


def cast(x: TensorRef, *, dtype: str, bitwidth: Optional[int] = None) -> TensorRef:
    return _single("cast", [x], hv_dim=x.hv_dim, dtype=dtype, input_datatype=x.dtype, output_datatype=dtype, output_bitwidth=bitwidth)


def place(
    x: TensorRef,
    *,
    memory_space: str,
    banking_factor: int = 1,
    storage_mode: str = "store",
    object_type: Optional[str] = None,
) -> TensorRef:
    return _single(
        "place",
        [x],
        hv_dim=x.hv_dim,
        dtype=x.dtype,
        role=x.role,
        memory_space=memory_space,
        banking_factor=banking_factor,
        storage_mode=storage_mode,
        object_type=object_type or x.object_type,
    )


def initialize_centroids(*, num_centroids: int, hv_dim: int, dtype: str = "binary", init_mode: str = "zero") -> TensorRef:
    return _single(
        "initialize_centroids",
        [],
        hv_dim=hv_dim,
        dtype=dtype,
        role="centroid_memory",
        num_centroids=num_centroids,
        init_mode=init_mode,
    )


def convergence_check(previous: TensorRef, current: TensorRef, *, threshold_value: float) -> TensorRef:
    return _single(
        "convergence_check",
        [previous, current],
        dtype="bool",
        role="convergence_flag",
        num_centroids=previous.shape[0] if previous.shape else None,
        threshold=threshold_value,
    )
