# Captions Chatbot

The Captions page now includes a small chat interface. Click **Chat** in the
Captions history tab to open a modal window where you can ask questions about
recent captions. The query sends up to the last 100 captions (or the selected
date range) to the language model configured by `CHATGPT_KEY`.
If more than 100 entries match your filters, the request is truncated and the
response notes the limitation. Both your question and the answer are appended to
the captions stream for reference.
