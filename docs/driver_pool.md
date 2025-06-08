# Browser Driver Management

Concurrent screenshot jobs previously reused a single global Selenium driver which led to `invalid session id` errors when threads collided. The driver is now stored in `threading.local()` so each thread gets its own browser instance. Every capture function calls `quit()` in a `finally` block and clears the thread-local slot so stale sessions are never reused.
