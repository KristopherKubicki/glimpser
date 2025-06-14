import os
import sys
from pathlib import Path

from scripts import generate_release_badges


def test_generate_release_badges(tmp_path):
    prev_cwd = os.getcwd()
    prev_env = os.environ.get("GITHUB_REF_NAME")
    os.chdir(tmp_path)
    os.environ["GITHUB_REF_NAME"] = "v9.9.9"
    try:
        generate_release_badges.main()
        badge_file = Path("release-badges.md")
        assert badge_file.exists()
        content = badge_file.read_text()
        for badge in generate_release_badges.BADGES:
            assert badge in content
    finally:
        os.chdir(prev_cwd)
        if prev_env is not None:
            os.environ["GITHUB_REF_NAME"] = prev_env
        else:
            os.environ.pop("GITHUB_REF_NAME", None)
