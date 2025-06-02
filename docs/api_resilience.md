# API Resilience

Glimpser interacts with external services such as camera endpoints and language models. Network issues or rate limits can cause these APIs to become temporarily unavailable. To avoid blocking the user interface, Glimpser now sends API requests with a timeout and retries using exponential backoff.

The helper `request_with_retry` in `app/utils/api_utils.py` wraps `requests.request` and will retry failed requests a few times, waiting longer between attempts. When the LLM summarization call fails after retries, the last cached summary is returned if available. Otherwise a short message such as "Summarization delayed" is provided so the UI continues to load.

This approach keeps the application responsive even when external services are slow or offline.
