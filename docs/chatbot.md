# Captions Chatbot

The Captions page now includes a small chat interface. Click **Chat** in the
Captions history tab to open a modal window where you can ask questions about
recent captions. The query sends up to the last 100 captions (or the selected
date range) to the language model configured by `CHATGPT_KEY`.
If more than 100 entries match your filters, the request is truncated and the
response notes the limitation. Both your question and the answer are appended to
the captions stream for reference.

### UI details

* The chat input is focused and cleared each time the modal opens for quicker
  follow‑up questions.
* Press **Enter** to submit and **Shift+Enter** for a new line.
* A "Thinking…" placeholder appears while the backend processes the request
  and a friendly error message is shown on network failure.
* The conversation history is displayed inside the modal and also added to the
  captions table.
* The dialog is accessible via the Escape key and uses `role="dialog"`.
