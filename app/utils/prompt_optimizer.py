"""Utility for generating optimized caption prompts."""

import os

import app.utils.image_processing as img_proc
from app.config import CHATGPT_KEY, LLM_CAPTION_PROMPT, SCREENSHOT_DIRECTORY
from app.utils.llm import ask_question

from .image_processing import ChatGPTImageComparison
from .template_manager import get_screenshots_for_template, get_templates


def generate_prompt(template_name: str, num_images: int = 3) -> str:
    """Return a suggested caption prompt for ``template_name``."""

    if not CHATGPT_KEY:
        return ""

    screenshots = get_screenshots_for_template(template_name)[:num_images]
    if not screenshots:
        return ""

    base = os.path.join(
        os.path.dirname(os.path.join(__file__)),
        "..",
        SCREENSHOT_DIRECTORY,
        template_name,
    )
    image_paths = [
        os.path.join(base, shot)
        for shot in screenshots
        if os.path.exists(os.path.join(base, shot))
    ]
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


def audit_prompts() -> dict[str, str]:
    """Return improved prompts for all templates using ChatGPT."""

    if not CHATGPT_KEY:
        return {}

    templates = get_templates()
    suggestions: dict[str, str] = {}
    for name, details in templates.items():
        note = details.get("notes", "").strip()
        if not note:
            continue
        question = (
            "Glimpser captions images using this core prompt: "
            f"{LLM_CAPTION_PROMPT}.\n"
            f"Current prompt for {name!r}: {note}\n"
            "Rewrite it more concisely. Return only the new text."
        )
        response = ask_question(question)
        if response:
            suggestions[name] = response.strip()
    return suggestions
