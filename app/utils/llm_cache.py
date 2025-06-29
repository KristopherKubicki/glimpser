"""Persist lightweight cache of LLM responses on disk.

Entries map a SHA-256 digest of the prompt and image list to the stored
text and token count.  The cache avoids repeated OpenAI API calls in
tests or when captions are requested frequently.  It loads lazily on
import and writes back automatically when new data is stored.
"""

import hashlib
import json
import logging
import os

CACHE_PATH = "data/llm_cache.json"
_cache = {}


def _load_cache() -> None:
    """Load cached responses from ``CACHE_PATH``."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    if not os.path.exists(CACHE_PATH):
        return
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
    except Exception:
        return
    _cache.clear()
    _cache.update(data)


def _persist_cache() -> None:
    """Persist ``_cache`` to ``CACHE_PATH``."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(_cache, f)
    except Exception:
        logging.exception("Failed to persist llm cache")


def _key(prompt: str, image_paths=None) -> str:
    if image_paths is None:
        image_paths = []
    digest = hashlib.sha256()
    digest.update(prompt.encode("utf-8"))
    for path in image_paths:
        digest.update(path.encode("utf-8"))
    return digest.hexdigest()


def get(prompt: str, image_paths=None):
    """Return cached entry for the ``prompt`` and ``image_paths`` if present."""
    key = _key(prompt, image_paths)
    entry = _cache.get(key)
    if entry is None:
        return None
    return entry


def store(prompt: str, response: str, tokens: int, image_paths=None) -> None:
    """Store the ``response`` and ``tokens`` for the given input."""
    key = _key(prompt, image_paths)
    _cache[key] = {"response": response, "tokens": int(tokens)}
    _persist_cache()


if not os.environ.get("PYTEST_CURRENT_TEST"):
    _load_cache()
