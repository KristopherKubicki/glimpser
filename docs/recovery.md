# Camera Recovery

Glimpser includes a manual recovery flow for broken public cameras. The Recovery button lives on each camera detail page and is designed to be human‑in‑the‑loop: it suggests alternatives, shows a preview, and only applies changes after you approve them.

## How It Works

1. Open a camera’s detail page.
2. Click **Recovery**.
3. Describe the camera (location, name, context).
4. Click **Search** to fetch public alternatives.
5. Preview candidates (short clips when possible) and **Apply Selected** if it looks right.

## Notes

- Only public URLs are considered.
- All URL changes require human approval.
- The system logs recovery searches and applied changes for auditability.

## Settings

- `RECOVERY_SEARCH_MODEL`: OpenAI model used for the web search step.
