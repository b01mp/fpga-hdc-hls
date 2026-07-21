from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


_ACTIVE_GRAPH: Optional["Graph"] = None


@dataclass(frozen=True)
class TensorRef:
    """Symbolic value carried between Python HDC API calls."""

    name: str
    shape: Tuple[int, ...] = ()
    dtype: str = "binary"
    hv_dim: Optional[int] = None
    role: str = "value"
    object_type: Optional[str] = None
    producer: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "shape": list(self.shape),
            "dtype": self.dtype,
            "hv_dim": self.hv_dim,
            "role": self.role,
            "object_type": self.object_type,
            "producer": self.producer,
        }


@dataclass(frozen=True)
class QuantizedRef:
    """Pair of symbolic index streams produced by quantize()."""

    feature_indices: TensorRef
    level_indices: TensorRef


@dataclass(frozen=True)
class Node:
    id: str
    op: str
    inputs: List[str]
    outputs: List[str]
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    value: str
    edge_policy: str = "local_buffer"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "value": self.value,
            "edge_policy": self.edge_policy,
        }


class Graph:
    """Typed HDC application graph captured from explicit API calls."""

    def __init__(self, name: str):
        self.name = name
        self.nodes: List[Node] = []
        self.edges: List[Edge] = []
        self.values: Dict[str, TensorRef] = {}
        self._value_users: Dict[str, List[str]] = {}

    @contextmanager
    def as_default(self) -> Iterator["Graph"]:
        global _ACTIVE_GRAPH
        previous = _ACTIVE_GRAPH
        _ACTIVE_GRAPH = self
        try:
            yield self
        finally:
            _ACTIVE_GRAPH = previous

    def add_input(
        self,
        name: str,
        *,
        shape: Iterable[int] = (),
        dtype: str = "binary",
        hv_dim: Optional[int] = None,
        role: str = "input",
        object_type: Optional[str] = None,
    ) -> TensorRef:
        ref = TensorRef(
            name=name,
            shape=tuple(shape),
            dtype=dtype,
            hv_dim=hv_dim,
            role=role,
            object_type=object_type,
        )
        self.values[name] = ref
        return ref

    def add_node(
        self,
        op: str,
        inputs: Iterable[TensorRef],
        *,
        params: Optional[Dict[str, Any]] = None,
        outputs: Optional[List[Dict[str, Any]]] = None,
        edge_policy: str = "local_buffer",
    ) -> List[TensorRef]:
        node_id = f"n{len(self.nodes)}_{op}"
        out_defs = outputs or [{}]
        output_refs: List[TensorRef] = []

        for idx, out_def in enumerate(out_defs):
            name = out_def.get("name", f"{node_id}_out{idx}")
            ref = TensorRef(
                name=name,
                shape=tuple(out_def.get("shape", ())),
                dtype=out_def.get("dtype", "binary"),
                hv_dim=out_def.get("hv_dim"),
                role=out_def.get("role", "value"),
                object_type=out_def.get("object_type"),
                producer=node_id,
            )
            self.values[name] = ref
            output_refs.append(ref)

        input_refs = list(inputs)
        node = Node(
            id=node_id,
            op=op,
            inputs=[ref.name for ref in input_refs],
            outputs=[ref.name for ref in output_refs],
            params=params or {},
        )
        self.nodes.append(node)

        for ref in input_refs:
            if ref.producer is not None:
                self.edges.append(Edge(src=ref.producer, dst=node_id, value=ref.name, edge_policy=edge_policy))
            self._value_users.setdefault(ref.name, []).append(node_id)

        return output_refs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application": self.name,
            "values": {name: ref.to_dict() for name, ref in self.values.items()},
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def active_graph() -> Graph:
    if _ACTIVE_GRAPH is None:
        raise RuntimeError("No active python_hdc.Graph. Use `with graph.as_default():`.")
    return _ACTIVE_GRAPH
