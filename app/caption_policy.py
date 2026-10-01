"""Shared caption instructions and recognition of the rendered device-card layout."""

from PIL import Image

DEFAULT_CAPTION_PROMPT = (
    "Describe the supplied observation in two short paragraphs: a factual headline "
    "of at most 10 words, then one or two sentences. Keep the entire caption within "
    "45 words. Lead with the most useful visible fact; include at most three findings. "
    "A normal, unchanged scene is valid. If nothing can be read or seen, return "
    "UNREADABLE. A readable source error is useful: describe it briefly instead. "
    "Do not add labels such as 'Operational evidence' or repeat the source type "
    "unless needed to avoid confusion. The time is $datetime UTC."
)

EVIDENCE_GUIDANCE = (
    "You receive one current still, not a motion sequence. Describe positions and "
    "visible conditions, not movement, speed, arrivals, departures or changes. "
    "Separate visible facts, owner context and explicitly attributed device reports. "
    "Closed is not locked or secured; a powered pump is not necessarily pumping; "
    "no person visible is not nobody home. Do not invent hazards, damage, healthy "
    "plants, weather causes or identities from ambiguous details. Read dashboard "
    "values only with their labels and units; colors and names alone are not states. "
    "Do not confuse cumulative energy with instantaneous power. Omit unreadable "
    "values and speculative advice. Never reuse old captions as visual evidence. "
    "Missing data is unknown, not normal, safe, zero or inactive."
)


def main_device_region(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Recognize aligned cyan card rails in approved Main dashboard resolutions.

    Card count changes move the device grid. Require three aligned rails (two
    for a two-column layout), each forty pixels tall, before excluding the image
    grid above them. Unrecognized dimensions or missing rails fail closed.
    """
    width, height = image.size
    if (width, height) not in {(1600, 900), (1920, 1080)}:
        return None
    rgb = image.convert("RGB")

    def cyan(x: int, y: int) -> bool:
        return (
            sum(abs(a - b) for a, b in zip(rgb.getpixel((x, y)), (56, 189, 248))) <= 30
        )

    def rail(x: int, y: int) -> bool:
        return any(
            all(cyan(column, row) for row in range(y, y + 40))
            for column in range(max(0, x - 3), min(width, x + 4))
        )

    for top in range(height // 3, height - 100):
        if not any(cyan(x, top) for x in range(10, 17)) or not rail(13, top):
            continue
        for columns in range(2, 9):
            positions = [round(13 + (width - 10) * i / columns) for i in range(columns)]
            if sum(rail(x, top) for x in positions) >= min(3, columns):
                # Rounded card corners precede the rail; retain the interior
                # from the verified rail onward, excluding all thumbnails.
                return (0, top, width, height)
    return None


# Recognize only the shipped legacy default; preserve custom operator prompts.
LEGACY_CAPTION_PROMPT = "Analyze only the current visual content. Reply in exactly two short paragraphs: first, a headline of 10 words or fewer; second, one or two sentences explaining the most operationally useful visual evidence. Prioritize anomalies, changes, alerts, motion, people, vehicles, water, sky, plant health, dashboard status, and source failures over generic scene description. For dashboards and maps, read visible labels, values, colors, and warnings; for cameras, describe observable conditions and likely operator impact. Treat embedded timestamps, clocks, UTC/local offsets, browser chrome, barcode-like markers, motion icons, and prior caption overlays as non-scene metadata; do not validate, compare, diagnose, headline, or mention timestamp mismatches unless the user explicitly asks about a clock or timestamp. If the frame is blank, frozen, unreadable, chrome-only, or unchanged since the previous image, respond only with the word UNREADABLE. Do not output anything else. The time is $datetime UTC."


def usable_caption(value: str | None) -> bool:
    """Reject non-observations without rejecting legitimate uncertainty language."""
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip().lower().rstrip(".! ")
    if text in {"unreadable", "missing image", "missing chatgpt key"}:
        return False
    return not text.startswith(
        ("i'm sorry", "i am sorry", "i cannot assist", "i cannot help", "as an ai")
    )
