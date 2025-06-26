"""CLIPProcessor helper used for object filtering.

This lightweight processor avoids pulling in the heavy ``transformers``
package. It provides just enough functionality for ONNX CLIP models.
"""
from __future__ import annotations

import numpy as np
from PIL import Image


class CLIPProcessor:
    """Minimal CLIP processor for ONNX models."""

    def __init__(self) -> None:
        pass

    @classmethod
    def from_pretrained(cls, _name: str) -> "CLIPProcessor":
        """Return a basic processor instance."""
        return cls()

    def __call__(self, text, images, return_tensors="np", padding=True):
        token_ids = [ord(c) for c in (text[0] if text else "")][:77]
        input_ids = np.zeros((1, 77), dtype=np.int64)
        attention_mask = np.zeros((1, 77), dtype=np.int64)
        input_ids[0, : len(token_ids)] = token_ids
        attention_mask[0, : len(token_ids)] = 1

        img = images.convert("RGB").resize((224, 224))
        img_array = (np.array(img).astype("float32") / 255.0).transpose(2, 0, 1)
        pixel_values = np.expand_dims(img_array, 0)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "pixel_values": pixel_values,
        }
