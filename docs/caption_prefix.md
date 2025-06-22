# Avoiding Caption Prefix Responses

Older versions of Glimpser sometimes displayed captions that began with
`Caption:` or `Title:`. The application now removes these prefixes and any
simple Markdown like `**bold**` before showing the text.

If you still encounter unwanted prefixes, verify you are running the latest
version. You can also add a line to `LLM_CAPTION_PROMPT` instructing the model
to reply with plain text only.
