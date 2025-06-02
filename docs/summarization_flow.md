# Summarization Flow

This document outlines how Glimpser generates captions and summaries from captured images.

1. **Frame Selection** – When motion is detected, `update_camera` picks the most relevant frames for the LLM:
   - `reference.png` if available.
   - `prev_motion.png` or the previous `last_motion.png` symlink.
   - The latest captured frame.
2. **Prompt Preparation** – Template notes are split on newlines and joined with the `---` separator to keep prompts concise.
3. **LLM Comparison** – The selected frames and prepared prompt are passed to `chatgpt_compare`, which calls the ChatGPT API to generate a caption.
4. **Summary Update** – Generated captions are stored and later aggregated by `update_summary` to produce a brief system-wide overview.

These steps ensure only meaningful frames are compared and prompts remain manageable for the language model.
