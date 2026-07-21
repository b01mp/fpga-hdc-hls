from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class HLSTemplate:
    op: str
    category: str
    header: str
    template: str
    supported_datatypes: List[str]
    knobs: List[str]
    characterization_sources: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


COMMON_DIM_KNOBS = ["hv_dim", "datatype", "bitwidth", "dimension_parallelism", "pipeline_mode"]
MEMORY_KNOBS = ["memory_space", "banking_factor", "storage_mode"]


_TEMPLATES: Dict[str, List[HLSTemplate]] = {
    "random_hv": [
        HLSTemplate(
            op="random_hv",
            category="generation",
            header="include/generation/random_hv.hpp",
            template="random_hv",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["seed_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "gen_levels": [
        HLSTemplate(
            op="gen_levels",
            category="generation",
            header="include/generation/gen_levels.hpp",
            template="gen_levels",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["num_levels", "level_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "rematerialize": [
        HLSTemplate(
            op="rematerialize",
            category="generation",
            header="include/generation/rematerialize.hpp",
            template="rematerialize",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["seed_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "quantize": [
        HLSTemplate(
            op="quantize",
            category="encoding",
            header="include/encoding/quantize.hpp",
            template="quantize",
            supported_datatypes=["float32", "fixed", "integer"],
            knobs=["num_features", "num_levels", "feature_parallelism", "datatype", "bitwidth", "pipeline_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "bind": [
        HLSTemplate(
            op="bind",
            category="encoding",
            header="include/encoding/bind.hpp",
            template="bind",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS,
            characterization_sources=["DSE/synth_results/characterize.csv", "DSE/synth_results/benchmarks.csv"],
        )
    ],
    "permute": [
        HLSTemplate(
            op="permute",
            category="encoding",
            header="include/encoding/permute.hpp",
            template="permute",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["shift"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "scale": [
        HLSTemplate(
            op="scale",
            category="encoding",
            header="include/encoding/scale.hpp",
            template="scale",
            supported_datatypes=["fixed", "integer"],
            knobs=COMMON_DIM_KNOBS,
            characterization_sources=["per_function_sweep"],
        )
    ],
    "gemm": [
        HLSTemplate(
            op="gemm",
            category="encoding",
            header="include/encoding/gemm.hpp",
            template="gemm",
            supported_datatypes=["fixed", "integer"],
            knobs=["rows", "cols", "inner_dim", "datatype", "bitwidth", "dimension_parallelism", "pipeline_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "matvec": [
        HLSTemplate(
            op="matvec",
            category="encoding",
            header="include/encoding/matvec.hpp",
            template="matvec",
            supported_datatypes=["fixed", "integer"],
            knobs=["rows", "cols", "datatype", "bitwidth", "dimension_parallelism", "pipeline_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "transpose": [
        HLSTemplate(
            op="transpose",
            category="encoding",
            header="include/encoding/transpose.hpp",
            template="transpose",
            supported_datatypes=["binary", "bipolar", "fixed", "integer"],
            knobs=["rows", "cols", "datatype", "bitwidth", "pipeline_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "flatten": [
        HLSTemplate(
            op="flatten",
            category="encoding",
            header="include/encoding/flatten.hpp",
            template="flatten",
            supported_datatypes=["binary", "bipolar", "fixed", "integer"],
            knobs=["input_shape", "datatype", "bitwidth", "pipeline_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "bundle": [
        HLSTemplate(
            op="bundle",
            category="aggregation",
            header="include/aggregation/bundle.hpp",
            template="bundle",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["num_vectors", "accumulator_bitwidth"],
            characterization_sources=["DSE/synth_results/characterize.csv"],
        )
    ],
    "threshold": [
        HLSTemplate(
            op="threshold",
            category="aggregation",
            header="include/aggregation/threshold.hpp",
            template="threshold",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["accumulator_bitwidth"],
            characterization_sources=["DSE/synth_results/characterize.csv", "DSE/synth_results/benchmarks.csv"],
        )
    ],
    "normalize": [
        HLSTemplate(
            op="normalize",
            category="aggregation",
            header="include/aggregation/normalize.hpp",
            template="normalize",
            supported_datatypes=["fixed", "integer"],
            knobs=COMMON_DIM_KNOBS + ["normalization_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "update": [
        HLSTemplate(
            op="update",
            category="aggregation",
            header="include/aggregation/update.hpp",
            template="update",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["update_mode", "learning_rate"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "cast": [
        HLSTemplate(
            op="cast",
            category="aggregation",
            header="include/aggregation/cast.hpp",
            template="cast",
            supported_datatypes=["binary", "bipolar", "fixed", "integer"],
            knobs=["input_datatype", "output_datatype", "input_bitwidth", "output_bitwidth", "hv_dim"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "similarity_search": [
        HLSTemplate(
            op="similarity_search",
            category="search",
            header="include/search/similarity_search.hpp",
            template="similarity_search",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["num_classes", "class_parallelism", "similarity_metric"],
            characterization_sources=["DSE/synth_results/characterize.csv", "DSE/synth_results/benchmarks.csv"],
        )
    ],
    "gather": [
        HLSTemplate(
            op="gather",
            category="memory",
            header="include/memory/gather.hpp",
            template="gather",
            supported_datatypes=["binary", "bipolar", "fixed", "integer"],
            knobs=COMMON_DIM_KNOBS + MEMORY_KNOBS + ["num_vectors"],
            characterization_sources=["DSE/synth_results/memory_sweep.csv"],
        )
    ],
    "place": [
        HLSTemplate(
            op="place",
            category="memory",
            header="include/memory/place.hpp",
            template="place",
            supported_datatypes=["binary", "bipolar", "fixed", "integer"],
            knobs=COMMON_DIM_KNOBS + MEMORY_KNOBS + ["object_type", "num_vectors"],
            characterization_sources=["DSE/synth_results/memory_sweep.csv"],
        )
    ],
    "initialize_centroids": [
        HLSTemplate(
            op="initialize_centroids",
            category="control",
            header="include/control/initialize_centroids.hpp",
            template="initialize_centroids",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=COMMON_DIM_KNOBS + ["num_centroids", "init_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
    "convergence_check": [
        HLSTemplate(
            op="convergence_check",
            category="control",
            header="include/control/convergence_check.hpp",
            template="convergence_check",
            supported_datatypes=["binary", "bipolar", "fixed"],
            knobs=["num_centroids", "threshold", "datatype", "bitwidth", "pipeline_mode"],
            characterization_sources=["per_function_sweep"],
        )
    ],
}

SUPPORTED_OPS = tuple(sorted(_TEMPLATES))


def get_templates(op: str) -> List[HLSTemplate]:
    return list(_TEMPLATES.get(op, []))


def registry_as_dict() -> Dict[str, List[Dict[str, object]]]:
    return {op: [template.to_dict() for template in templates] for op, templates in _TEMPLATES.items()}
