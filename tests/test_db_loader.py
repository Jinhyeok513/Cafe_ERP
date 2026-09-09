from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cafe_stock_manage.db_loader import (  # noqa: E402
    DatasetLoadError,
    build_import_sql,
    validate_dataset,
)
from cafe_stock_manage.synthetic import (  # noqa: E402
    generate_dataset,
    load_config,
    write_dataset,
)


class DatabaseLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(PROJECT_ROOT / "config" / "prototype_assumptions.json")

    def write_temporary_dataset(self, directory: Path, scenario: str = "clean") -> None:
        dataset = generate_dataset(self.config, scenario=scenario)
        write_dataset(dataset, self.config, directory, scenario=scenario)

    def test_generated_dataset_passes_file_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_dir = Path(temporary_directory)
            self.write_temporary_dataset(dataset_dir, scenario="errors")

            manifest = validate_dataset(dataset_dir)

            self.assertEqual(manifest["scenario"], "errors")
            self.assertEqual(manifest["files"]["scenario_events.csv"]["rows"], 9)

    def test_modified_csv_is_rejected_before_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_dir = Path(temporary_directory)
            self.write_temporary_dataset(dataset_dir)
            with (dataset_dir / "calendar.csv").open("a", encoding="utf-8") as csv_file:
                csv_file.write("tampered,row\n")

            with self.assertRaisesRegex(DatasetLoadError, "Checksum mismatch"):
                validate_dataset(dataset_dir)

    def test_import_sql_uses_transaction_and_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_dir = Path(temporary_directory)
            self.write_temporary_dataset(dataset_dir)
            manifest = validate_dataset(dataset_dir)

            sql = build_import_sql(dataset_dir, manifest, reset=True)

            self.assertIn("BEGIN;", sql)
            self.assertIn("TRUNCATE TABLE", sql)
            self.assertIn("FROM data_quality_issues", sql)
            self.assertIn("COMMIT;", sql)


if __name__ == "__main__":
    unittest.main()
