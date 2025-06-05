# HTTP/2 Push for sprite.svg

The icon sprite used by the interface can be preloaded by the browser. When serving Glimpser behind Nginx, enable HTTP/2 server push so the sprite arrives with the initial page request.

Add the following to your `location /` block:

```nginx
location / {
    http2_push /static/icons/sprite.svg;
}
```

Combined with the `<link rel="preload" href="/static/icons/sprite.svg" as="image" type="image/svg+xml" crossorigin>` tag in `header.html`, pushing the sprite saves roughly 120&nbsp;ms on a 4G connection.
