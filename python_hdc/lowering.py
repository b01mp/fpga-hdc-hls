from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .graph import Graph
from .registry import get_templates


def lower_to_dse_spec(
    graph: Graph,
    *,
    target_fpga: str = "u280",
    clock_mhz: int = 250,
    default_edge_policy: str = "local_buffer",
) -> Dict[str, Any]:
    """Lower a captured HDC graph to a DSE-facing candidate specification."""

    graph_dict = graph.to_dict()
    nodes = []
    for node in graph.nodes:
        candidates = [template.to_dict() for template in get_templates(node.op)]
        nodes.append(
            {
                **node.to_dict(),
                "candidates": candidates,
            }
        )

    edges = []
    for edge in graph.edges:
        edge_dict = edge.to_dict()
        edge_dict.setdefault("edge_policy", default_edge_policy)
        edges.append(edge_dict)

    return {
        "application": graph.name,
        "target": {
            "fpga": target_fpga,
            "clock_mhz": clock_mhz,
        },
        "values": graph_dict["values"],
        "nodes": nodes,
        "edges": edges,
        "lowering": {
            "type": "explicit_hdc_api",
            "scope": "registered_hls_templates",
            "default_edge_policy": default_edge_policy,
        },
    }


def write_dse_spec(graph: Graph, path: str | Path, **kwargs: Any) -> Dict[str, Any]:
    spec = lower_to_dse_spec(graph, **kwargs)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec
