from pathlib import Path
import unittest

from novel_factory.acs_novel_factory.center.knowledge import KnowledgeStore


class KnowledgeSmokeTest(unittest.TestCase):
    def test_knowledge_snapshot_loads(self) -> None:
        root = Path(__file__).resolve().parents[1]
        snapshot = KnowledgeStore(root / "knowledge").snapshot()
        self.assertEqual(snapshot["characters"][0]["id"], "knowledge.character.0001")
        self.assertEqual(snapshot["realms"][0]["name"], "炼气期")
