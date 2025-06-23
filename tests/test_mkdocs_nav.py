import unittest
from pathlib import Path

import yaml


class TestMkdocsNav(unittest.TestCase):
    def _collect_paths(self, entries):
        for item in entries:
            if isinstance(item, dict):
                for value in item.values():
                    if isinstance(value, list):
                        yield from self._collect_paths(value)
                    elif isinstance(value, str):
                        yield value
            elif isinstance(item, str):
                yield item

    def test_nav_files_exist(self):
        config = yaml.safe_load(Path("mkdocs.yml").read_text())
        docs_dir = Path(config.get("docs_dir", "docs"))
        for rel in self._collect_paths(config.get("nav", [])):
            if rel.endswith(".md"):
                path = docs_dir / rel
                self.assertTrue(path.exists(), f"Missing {path}")


if __name__ == "__main__":
    unittest.main()
