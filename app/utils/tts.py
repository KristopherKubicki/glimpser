# app/utils/tts.py

try:
    import pyttsx3
except Exception:  # pragma: no cover - optional dependency
    pyttsx3 = None


def generate_tts(text: str, output_path: str) -> None:
    """Generate a speech audio file from ``text`` and save it to ``output_path``."""
    if not text:
        return

    if pyttsx3 is None:
        return

    engine = pyttsx3.init()
    try:
        engine.save_to_file(text, output_path)
        engine.runAndWait()
    finally:
        engine.stop()
