# Template Clip Caching

Template thumbnails load a short preview video when visible. The high-quality clip from `/clip/<template>` now downloads only once every two minutes. A small client-side cache stores the clip so revisiting the tile won't hit the server again until the cache expires.
