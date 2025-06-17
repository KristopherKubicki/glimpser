# API Resilience

Glimpser interacts with external services such as camera endpoints and language models. Network issues or rate limits can cause these APIs to become temporarily unavailable. To avoid blocking the user interface, Glimpser now sends API requests with a timeout and retries using exponential backoff. The default timeout for these requests is **30 seconds**.

The helper `request_with_retry` in `app/utils/api_utils.py` wraps `requests.request` and will retry failed requests a few times, waiting longer between attempts. LLM requests now wait up to **30 seconds** for OpenAI before retrying, which helps during cold starts. When the summarization call still fails after retries, the last cached summary is returned if available. Otherwise a short message such as "Summarization delayed" is provided so the UI continues to load.

This approach keeps the application responsive even when external services are slow or offline.

The scheduler now calls `is_system_online` before launching subprocesses. If the system is offline, jobs are skipped and marked offline instead of failing with file descriptor errors. The helper checks each address listed in the `ONLINE_TEST_HOSTS` environment variable (default `8.8.8.8,1.1.1.1`) and returns online if any respond. The target port can be overridden with `ONLINE_TEST_PORT` (default `443`). If none of the hosts respond but at least one non-loopback interface is up, the helper assumes local network connectivity and logs `offline check fallback: LAN interface active`.

Skipped jobs are stored in the `offline_jobs` table. A background task checks connectivity every 30 seconds and re-runs any queued tasks once the system comes back online.

Screenshot capture routines now call `is_system_online` before trying to download a browser driver. When offline the capture is skipped and a warning is logged instead of raising network errors.
