# API Resilience

Glimpser interacts with external services such as camera endpoints and language models. Network issues or rate limits can cause these APIs to become temporarily unavailable. To avoid blocking the user interface, Glimpser now sends API requests with a timeout and retries using exponential backoff. The default timeout for these requests is **30 seconds**.

The helper `request_with_retry` in `app/utils/api_utils.py` wraps `requests.request` and will retry failed requests a few times, waiting longer between attempts. LLM requests now wait up to **30 seconds** for OpenAI before retrying, which helps during cold starts. When the summarization call still fails after retries, the last cached summary is returned if available. Otherwise a short message such as "Summarization delayed" is provided so the UI continues to load.

This approach keeps the application responsive even when external services are slow or offline.

The scheduler now calls `is_system_online` before launching subprocesses. If the system is offline, jobs are skipped and marked offline instead of failing with file descriptor errors. The helper first probes the `ONLINE_TEST_URLS` environment variable (default `https://connectivitycheck.gstatic.com/generate_204`). If any URL responds to a HEAD request, the system is considered online. Otherwise the helper checks each address listed in `ONLINE_TEST_HOSTS` (default `8.8.8.8,1.1.1.1`). Hosts can include a custom port using the `host:port` syntax, otherwise `ONLINE_TEST_PORT` (default `443`) is used. When all probes fail, a grace window (`OFFLINE_GRACE_SECONDS`, default 300) keeps the system in a best-effort online state if a recent probe succeeded.

Glimpser also tracks LAN, WAN, and DNS health separately. Configure `LAN_TEST_HOSTS` (for local IPs), `DNS_TEST_HOSTS` (resolver IPs to probe), and optional grace windows (`LAN_GRACE_SECONDS`, `WAN_GRACE_SECONDS`, `DNS_GRACE_SECONDS`) to keep local captures running even when WAN/DNS is degraded. Repeated failures on local devices trigger a quarantine window (`PREFLIGHT_LOCAL_QUARANTINE_*`) to avoid hammering offline cameras.

Preflight reachability checks now cache socket results per host/port to reduce repeated probes during flaky conditions. Tune the cache with `PREFLIGHT_REACHABILITY_TTL` and `PREFLIGHT_REACHABILITY_BACKOFF`. RTSP OPTIONS/keepalive probes are likewise cached using `PREFLIGHT_RTSP_PROBE_TTL` and `PREFLIGHT_RTSP_KEEPALIVE_TTL` to avoid hammering unstable streams.

DNS and TLS preflight caches honor `PREFLIGHT_DNS_CACHE_TTL` and `PREFLIGHT_TLS_CACHE_TTL`, allowing you to shorten or extend hostname/TLS cache lifetimes when the network is noisy.

DNS resolution lookups for reachability checks are also cached using `PREFLIGHT_DNS_RESOLVE_TTL` to reduce repeated resolver hits when targets are stable.

Renderer health is tracked to avoid repeatedly launching unstable renderers. When lightweight, PhantomJS, or headless renderers fail, Glimpser backs off for `PREFLIGHT_RENDERER_FAIL_TTL` seconds before retrying.

HTML sources that repeatedly report `not_modified` are treated as stable and placed into a short backoff (`PREFLIGHT_HTML_STABLE_*`). Large HTML payloads can skip heavy render stages once they exceed `PREFLIGHT_HTML_MAX_BYTES`.

LLM rate limits are dampened with a rolling window and hard backoff (`LLM_429_WINDOW_SECONDS`, `LLM_429_HARD_LIMIT`, `LLM_429_HARD_BACKOFF_MINUTES`) so a temporary burst does not flood logs or thrash retries.

HTTP/3 hints are cached from `Alt-Svc` headers, but hosts that show protocol issues are downgraded to HTTP/1/2 using `PREFLIGHT_H3_DOWNGRADE_TTL` (or forced via `PREFLIGHT_FORCE_H3_DOWNGRADE`).

HTTP/2 downgrade hints are cached with `PREFLIGHT_H2_DOWNGRADE_TTL`, so endpoints that misbehave on h2 can be retried with h1-style headers for a while before re-testing.

Preflight now tracks session cookie churn and static asset stability. Repeated `Set-Cookie` headers trigger a short backoff (`PREFLIGHT_COOKIE_CHURN_*`). Image/static URLs that keep returning unchanged `ETag`/`Last-Modified` headers are treated as stable assets and placed into a longer backoff (`PREFLIGHT_STATIC_ASSET_*`) to avoid heavy polling.

Optional heavy-stage probes help avoid expensive capture attempts. `PREFLIGHT_FFMPEG_NULL_PROBE` (default true) runs a short ffmpeg null-mux probe before full stream capture, and `PREFLIGHT_YTDLP_SIMULATE` (default true) runs `yt-dlp --simulate` before invoking ffmpeg on enhanced sources.

Skipped jobs are stored in the `offline_jobs` table. A background task checks connectivity every 30 seconds and re-runs any queued tasks once the system comes back online.

Screenshot capture routines now call `is_system_online` before trying to download a browser driver. When offline, Glimpser will still attempt to use a cached/system `chromedriver` if available; otherwise the capture is skipped and a warning is logged instead of raising network errors.
