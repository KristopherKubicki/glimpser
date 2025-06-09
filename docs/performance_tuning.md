# Performance Tuning

Glimpser avoids launching duplicate capture jobs to reduce CPU load. Each running job is tracked in `app/utils/scheduling.py` via the global `active_jobs` dictionary guarded by a lock. When a job is already active for a camera, new requests are skipped.

If a capture job repeatedly fails or times out, the scheduler backs off before
retrying. The delay grows exponentially up to five minutes, preventing the
system from thrashing when a camera remains offline.
