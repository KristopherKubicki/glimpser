# Bundle Size Audit

`npm run size-audit` checks the gzipped size of every JavaScript file under `app/static/js`.
If any file exceeds **140&nbsp;KiB**, the command fails so pages stay lightweight on mobile.
