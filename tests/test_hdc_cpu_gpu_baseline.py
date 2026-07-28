import csv
import tempfile
import unittest
from pathlib import Path

try:
    import torch
except ImportError:  # pragma: no cover - exercised only on machines without torch
    torch = None

from baselines import hdc_cpu_gpu_baseline as baseline


@unittest.skipIf(torch is None, "PyTorch is required for the CPU/GPU baseline")
class BinaryHdcBaselineTest(unittest.TestCase):
    def test_binary_primitives_match_hls_baseline_semantics(self):
        codebook = torch.tensor(
            [[0, 1, 1, 0], [1, 0, 1, 1], [1, 1, 0, 0]], dtype=torch.bool
        )
        gathered = baseline.gather(codebook, torch.tensor(1))
        self.assertTrue(torch.equal(gathered, torch.tensor([1, 0, 1, 1], dtype=torch.bool)))

        bound = baseline.bind(
            torch.tensor([0, 1, 1, 0], dtype=torch.bool),
            torch.tensor([1, 1, 0, 0], dtype=torch.bool),
        )
        self.assertTrue(torch.equal(bound, torch.tensor([1, 0, 1, 0], dtype=torch.bool)))

        hvs = torch.tensor(
            [[1, 0, 1, 0], [1, 1, 0, 0], [0, 1, 1, 0]], dtype=torch.bool
        )
        acc = baseline.bundle(hvs)
        self.assertTrue(torch.equal(acc, torch.tensor([2, 2, 2, 0], dtype=torch.int32)))

        thresholded = baseline.threshold(acc, count=3)
        self.assertTrue(torch.equal(thresholded, torch.tensor([1, 1, 1, 0], dtype=torch.bool)))

        query = torch.tensor([1, 0, 1, 0], dtype=torch.bool)
        prototypes = torch.tensor(
            [[1, 1, 1, 0], [1, 0, 1, 0], [0, 0, 0, 0]], dtype=torch.bool
        )
        pred = baseline.similarity_search(query, prototypes)
        self.assertEqual(int(pred.item()), 1)

    def test_image_classification_path_is_deterministic(self):
        inputs = baseline.make_inputs(
            device=torch.device("cpu"),
            hv_dim=64,
            num_features=8,
            num_levels=4,
            num_classes=3,
            seed=7,
        )

        first = baseline.image_classification(inputs)
        second = baseline.image_classification(inputs)
        self.assertEqual(int(first.item()), int(second.item()))
        self.assertGreaterEqual(int(first.item()), 0)
        self.assertLess(int(first.item()), 3)

    def test_runner_writes_expected_csv_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_csv = Path(tmpdir) / "baseline.csv"
            rows = baseline.run_suite(
                devices=[torch.device("cpu")],
                mode="all",
                hv_dim=32,
                num_features=4,
                num_levels=4,
                num_classes=3,
                warmup=1,
                repeat=2,
                seed=11,
                output=out_csv,
            )

            self.assertTrue(out_csv.exists())
            self.assertGreaterEqual(len(rows), 6)

            with out_csv.open(newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, baseline.CSV_FIELDS)
                parsed = list(reader)

            self.assertEqual(len(parsed), len(rows))
            self.assertIn("latency_mean_us", parsed[0])
            self.assertIn("power_source", parsed[0])
            self.assertEqual({row["backend"] for row in parsed}, {"cpu"})


if __name__ == "__main__":
    unittest.main()
