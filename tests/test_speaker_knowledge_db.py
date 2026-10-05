import tempfile
import unittest
from pathlib import Path

from scripts.system_design.speaker_knowledge_db import (
    DEFAULT_SEED,
    build_database,
    search_knowledge,
    workflow_stages,
)


class SpeakerKnowledgeDatabaseTests(unittest.TestCase):
    def test_build_and_search_preserves_sources_and_implementation_refs(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "knowledge.sqlite3"
            counts = build_database(DEFAULT_SEED, database)
            self.assertGreater(counts["sources"], 5)
            self.assertGreater(counts["knowledge_items"], 10)
            results = search_knowledge("Qes", database)
        self.assertTrue(results)
        self.assertTrue(results[0]["implementation_ref"])
        self.assertTrue(results[0]["sources"])

    def test_workflow_stages_are_sequential(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "knowledge.sqlite3"
            build_database(DEFAULT_SEED, database)
            stages = workflow_stages(database)
        self.assertEqual([stage["sequence"] for stage in stages],
                         sorted(stage["sequence"] for stage in stages))
        self.assertTrue(all(stage["gate"] for stage in stages))

    def test_search_includes_limitations_and_unavailable_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "knowledge.sqlite3"
            build_database(DEFAULT_SEED, database)
            limitations = search_knowledge("nonlinear", database)
            unavailable = search_knowledge("VituixCAD", database)
        self.assertTrue(any(item["record_type"] == "limitation" for item in limitations))
        self.assertTrue(any(item["record_type"] == "source" for item in unavailable))


if __name__ == "__main__":
    unittest.main()