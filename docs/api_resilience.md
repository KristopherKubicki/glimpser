# API Resilience

Glimpser interacts with external services such as camera endpoints and language models. Network issues or rate limits can cause these APIs to become temporarily unavailable. To avoid blocking the user interface, Glimpser now sends API requests with a timeout and retries using exponential backoff. The default timeout for these requests is **30 seconds**.

The helper `request_with_retry` in `app/utils/api_utils.py` wraps `requests.request` and will retry failed requests a few times, waiting longer between attempts. When the LLM summarization call fails after retries, the last cached summary is returned if available. Otherwise a short message such as "Summarization delayed" is provided so the UI continues to load.

This approach keeps the application responsive even when external services are slow or offline.

The scheduler now calls `is_system_online` before launching subprocesses. If the system is offline, jobs are skipped and marked offline instead of failing with file descriptor errors. The helper checks each address listed in the `ONLINE_TEST_HOSTS` environment variable (default `8.8.8.8,1.1.1.1`) and returns online if any respond.
