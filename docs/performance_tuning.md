# Performance Tuning

Glimpser avoids launching duplicate capture jobs to reduce CPU load. Each running job is tracked in `app/utils/scheduling.py` via the global `active_jobs` dictionary guarded by a lock. When a job is already active for a camera, new requests are skipped.

If a capture job repeatedly fails or times out, the scheduler backs off before
retrying. The delay grows exponentially up to five minutes, preventing the
system from thrashing when a camera remains offline.

When supported, hardware acceleration is enabled automatically to offload video
processing to the GPU. The default ffmpeg thread count also scales with the
number of CPU cores so lightweight systems don't get overwhelmed.

Crawler startups are spread automatically using a mathematical scheduler that
minimizes simultaneous runs. At launch, each crawler is assigned an offset based
on its frequency so heavy jobs are distributed evenly over the window defined by
`CRAWLER_STARTUP_SPREAD`.

Dashboard thumbnails now lazy load. Each video tile sets its poster image only
when it enters the viewport, reducing initial network requests for large setups.

The template grid uses a small virtual list so the DOM only contains tiles that
are near the viewport. As you scroll, new elements stream in while offscreen
tiles are discarded. This keeps interactions smooth even with dozens of
cameras.
