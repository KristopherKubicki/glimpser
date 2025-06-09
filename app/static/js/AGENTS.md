Use ES modules and keep functions small.
Lint and format code with `prettier` and `eslint`.
Add corresponding Jest tests under `tests/js`.
Avoid browser-specific APIs without feature detection.
Design DNA: Glanceable Ambient UI – dark-first, minimal controls, gesture driven.
Mobile-first; every page must pass npm run size-audit (< 140KiB gz).
Never block event-loop; async/await + timeout guard on network I/O.
Add/extend tests/ for each PR. npm t must be green.
Perf Budget: < 100 ms TTI on Pixel 6 (Lighthouse “timespan” run).
