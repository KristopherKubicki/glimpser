"""Caption policy, layout and cache regression coverage without model requests."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.caption_policy import (
    DEFAULT_CAPTION_PROMPT,
    LEGACY_CAPTION_PROMPT,
    main_device_region,
    usable_caption,
)
from app.utils import image_processing as processing
from app.utils import scheduling


def dashboard(width=1920, height=1080, top=490, columns=4):
    image = Image.new("RGB", (width, height), "#101827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, width - 20, top - 10), fill="red")
    for i in range(columns):
        x = round(13 + (width - 10) * i / columns)
        draw.rectangle((x, top + 2, x + 3, top + 100), fill="#38bdf8")
    return image


@pytest.mark.parametrize(
    "width,height,top,columns",
    [(1920, 1080, 490, 4), (1920, 1080, 636, 5), (1600, 900, 616, 4)],
)
def test_device_region_tracks_card_grid_and_excludes_thumbnails(
    tmp_path, width, height, top, columns
):
    image = dashboard(width, height, top, columns)
    path = tmp_path / "frame.png"
    image.save(path)
    box = main_device_region(image)
    assert box is not None and top <= box[1] <= top + 5
    with processing._caption_analysis_paths("HubitatMain", [str(path)]) as paths:
        assert len(paths) == 1
        with Image.open(paths[0]) as cropped:
            assert cropped.size == (width, height - box[1])
            assert (255, 0, 0) not in set(cropped.get_flattened_data())
    assert not Path(paths[0]).exists()
    assert Image.open(path).size == (width, height)


@pytest.mark.parametrize(
    "image",
    [Image.new("RGB", (1920, 1080)), dashboard(1280, 720, 400), dashboard(columns=1)],
)
def test_unrecognized_device_layout_is_rejected(image):
    assert main_device_region(image) is None


def test_legacy_default_is_normalized_without_changing_custom_prompts(monkeypatch):
    monkeypatch.setattr(processing, "LLM_CAPTION_PROMPT", LEGACY_CAPTION_PROMPT)
    prompt = processing._caption_system_prompt()
    assert "or unchanged since the previous image" not in prompt
    assert "45 words" in prompt
    assert "one current still" in prompt
    assert "forecast valid times" in prompt
    monkeypatch.setattr(
        processing, "LLM_CAPTION_PROMPT", "Operator-specific measurement guidance"
    )
    assert processing._caption_system_prompt().startswith(
        "Operator-specific measurement guidance"
    )


def test_both_caption_caches_change_identity_when_policy_changes(monkeypatch):
    monkeypatch.setattr(processing, "LLM_CAPTION_PROMPT", DEFAULT_CAPTION_PROMPT)
    first_image = processing._caption_cache_prompt("Example")
    first_scene = scheduling._scene_caption_cache_key("same-frame", "Example")
    monkeypatch.setattr(
        processing,
        "LLM_CAPTION_PROMPT",
        DEFAULT_CAPTION_PROMPT + " Read a specific gauge.",
    )
    assert processing._caption_cache_prompt("Example") != first_image
    assert scheduling._scene_caption_cache_key("same-frame", "Example") != first_scene
    assert scheduling._scene_caption_cache_key(
        "same-frame", "Example"
    ) == scheduling._scene_caption_cache_key("same-frame", "Example")


@pytest.mark.parametrize(
    "text",
    [
        "UNREADABLE",
        "Missing image",
        "Missing ChatGPT key",
        "I cannot assist with that",
        "",
        None,
    ],
)
def test_failure_text_is_not_a_caption(text):
    assert not usable_caption(text)


@pytest.mark.parametrize(
    "text",
    [
        "Gauge cannot be read in this frame.",
        "Sign reads sorry, closed today.",
        "No person visible; lock state cannot be determined.",
    ],
)
def test_uncertainty_is_not_mistaken_for_model_refusal(text):
    assert usable_caption(text)


def test_only_current_frame_reaches_caption_backend(tmp_path, monkeypatch):
    from unittest.mock import Mock

    current = tmp_path / "current.png"
    Image.new("RGB", (32, 32)).save(current)
    monkeypatch.setattr(processing, "CHATGPT_KEY", "fixture")
    monkeypatch.setattr(processing.llm_cache, "get", lambda *args: None)
    monkeypatch.setattr(processing.llm_cache, "store", lambda *args: None)
    compare = Mock(return_value=("A readable scene", 0))
    monkeypatch.setattr(processing.ChatGPTImageComparison, "compare_images", compare)
    assert (
        processing.chatgpt_compare(
            "Example", [str(tmp_path / "missing-old.png"), str(current)]
        )
        == "A readable scene"
    )
    assert compare.call_args.args[1] == [str(current)]
    compare.reset_mock()
    assert (
        processing.chatgpt_compare(
            "Example", [str(current), str(tmp_path / "missing-new.png")]
        )
        is None
    )
    compare.assert_not_called()
