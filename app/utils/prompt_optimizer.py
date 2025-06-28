"""Utility for generating optimized caption prompts."""

from pathlib import Path

import app.utils.image_processing as img_proc
from app.config import CHATGPT_KEY, SCREENSHOT_DIRECTORY

from .image_processing import ChatGPTImageComparison
from .template_manager import get_screenshots_for_template


def generate_prompt(template_name: str, num_images: int = 3) -> str:
    """Return a suggested caption prompt for ``template_name``."""

    if not CHATGPT_KEY:
        return ""

    screenshots = get_screenshots_for_template(template_name)[:num_images]
    if not screenshots:
        return ""

    base = Path(__file__).resolve().parent.parent / SCREENSHOT_DIRECTORY / template_name
    image_paths = [str(base / shot) for shot in screenshots if (base / shot).exists()]
    if not image_paths:
        return ""

    new_prompt = "Review the images and provide a short caption prompt to improve future captions."
    original_prompt = img_proc.LLM_CAPTION_PROMPT
    img_proc.LLM_CAPTION_PROMPT = new_prompt
    try:
        comparer = ChatGPTImageComparison()
        result, _ = comparer.compare_images("", image_paths, tokens=32)
    finally:
        img_proc.LLM_CAPTION_PROMPT = original_prompt

    return result or ""
