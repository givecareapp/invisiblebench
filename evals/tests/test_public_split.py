"""Every evals case is public: no held-out or confidential split can live here."""

import json
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
PUBLIC_SPLITS = {"core-behaviors", "red-team", "reddit-caregivers", "multi-turn"}


class PublicSplitTest(unittest.TestCase):
    def test_every_case_is_in_a_public_split(self) -> None:
        for path in sorted(DATA.glob("*.jsonl")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                with self.subTest(file=path.name, line=number):
                    self.assertIn(record["split"], PUBLIC_SPLITS)
                    self.assertFalse({"heldout", "held_out", "confidential"} & set(record))

    def test_no_heldout_files(self) -> None:
        names = [p.name.lower() for p in DATA.parent.rglob("*") if p.is_file()]
        self.assertFalse([n for n in names if "heldout" in n or "held-out" in n or "confidential" in n])


if __name__ == "__main__":
    unittest.main()
