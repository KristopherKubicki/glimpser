The application now enforces a strict Content Security Policy (CSP) on all responses.
The policy restricts resources to the local origin and allows images from data and
blob URLs:

```
Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:
```

This reduces the risk of cross-site scripting (XSS) and prevents mixed‑content
warnings when running behind corporate proxies.


