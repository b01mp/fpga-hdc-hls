import json
import unittest

import python_hdc as hdc
from python_hdc.lowering import lower_to_dse_spec
from python_hdc.registry import SUPPORTED_OPS, get_templates


class PythonHdcApiTest(unittest.TestCase):
    def test_api_records_typed_image_classification_graph(self):
        graph = hdc.Graph("image_classification")
        with graph.as_default():
            features = hdc.input_tensor("features", shape=(784,), dtype="float32")
            item_memory = hdc.memory("item_memory", object_type="codebook", num_vectors=784, hv_dim=1024)
            level_memory = hdc.memory("level_memory", object_type="codebook", num_vectors=32, hv_dim=1024)
            prototypes = hdc.memory("prototypes", object_type="prototype", num_vectors=10, hv_dim=1024)

            quantized = hdc.quantize(features, num_levels=32)
            item_hv = hdc.gather(item_memory, quantized.feature_indices, hv_dim=1024, role="item_hv")
            level_hv = hdc.gather(level_memory, quantized.level_indices, hv_dim=1024, role="level_hv")
            encoded = hdc.bind(item_hv, level_hv, hv_dim=1024)
            bundled = hdc.bundle(encoded, hv_dim=1024, num_vectors=784)
            query = hdc.threshold(bundled, hv_dim=1024, dtype="binary")
            prediction = hdc.similarity_search(query, prototypes, num_classes=10, metric="hamming")

        self.assertEqual(prediction.role, "class_id")
        self.assertEqual([node.op for node in graph.nodes], [
            "quantize",
            "gather",
            "gather",
            "bind",
            "bundle",
            "threshold",
            "similarity_search",
        ])
        self.assertEqual(graph.nodes[3].params["hv_dim"], 1024)
        self.assertEqual(graph.nodes[-1].params["metric"], "hamming")

    def test_supported_ops_have_hls_templates(self):
        missing = [op for op in SUPPORTED_OPS if not get_templates(op)]
        self.assertEqual(missing, [])

        bind_templates = get_templates("bind")
        self.assertEqual(bind_templates[0].header, "include/encoding/bind.hpp")
        self.assertIn("dimension_parallelism", bind_templates[0].knobs)

    def test_lowering_exports_dse_spec_with_candidate_templates(self):
        graph = hdc.Graph("tiny")
        with graph.as_default():
            a = hdc.input_hv("a", hv_dim=256, dtype="binary")
            b = hdc.input_hv("b", hv_dim=256, dtype="binary")
            out = hdc.bind(a, b, hv_dim=256)
            hdc.threshold(out, hv_dim=256, dtype="binary")

        spec = lower_to_dse_spec(graph, target_fpga="u280", clock_mhz=250)
        encoded = json.dumps(spec)

        self.assertEqual(spec["application"], "tiny")
        self.assertEqual(spec["target"]["fpga"], "u280")
        self.assertEqual(spec["nodes"][0]["op"], "bind")
        self.assertEqual(spec["nodes"][0]["candidates"][0]["template"], "bind")
        self.assertIn('"edge_policy"', encoded)
        self.assertIn('"local_buffer"', encoded)


if __name__ == "__main__":
    unittest.main()
