# LLM Prompt Settings

Glimpser uses long prompts to instruct the language model when generating summaries and image captions. These prompts can be overridden with environment variables or through the Settings page under **Advanced Options**.

Both prompts support the special `$datetime` token. When the model request is built, `$datetime` is replaced with the current UTC timestamp in ISO 8601 format.

## LLM_SUMMARY_PROMPT

`LLM_SUMMARY_PROMPT` provides the system message for log summaries. The default text encourages concise, technical narration and groups related insights. A shortened example is shown below:

```text
Return one single line of plain text—no line breaks... The time is $datetime UTC.
```

To override the prompt in your `.env` file, use a multi‑line value for readability:

```env
LLM_SUMMARY_PROMPT="
Return one single line of plain text with grouped insights.
Mark critical items with ⚠️ and resolved items with ✔️.
The time is \$datetime UTC."
```

The default prompt now aims for a five‑minute narration. It instructs the model
to write around sixty short lines, each starting with the camera name in square
brackets such as `[cam1]`. Stand‑alone `[pause]` lines mark brief silences so
the output works as a caption script when paired with video clips.

## LLM_CAPTION_PROMPT

`LLM_CAPTION_PROMPT` controls how image captions are generated. It requests a short headline and a brief explanation, replying with `UNREADABLE` if the frame lacks useful detail.

```text
Examine the image carefully, then reply in two paragraphs only... The time is $datetime UTC.
```

You can also supply a multi‑line value:

```env
LLM_CAPTION_PROMPT="
Examine the image and write a short headline.
If the frame is blank, output UNREADABLE.
The time is \$datetime UTC."
```

Each time a request is made, `$datetime` is swapped with the current time so the model can reference when the analysis occurred.

The Settings page also provides tooltips for these fields summarizing the
multi-line syntax and `$datetime` token. Hover over **LLM_SUMMARY_PROMPT** or
**LLM_CAPTION_PROMPT** to see a quick reminder when editing.
