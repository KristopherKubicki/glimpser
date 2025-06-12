# Braille Loading Spinner

Videos initially display the quick `/last_video` clip while the full `/clip` file loads.
A small braille spinner appears over the thumbnail until the HD video is ready.
This keeps pages responsive and provides visual feedback that higher quality
footage is on the way. The dashboard now loads HD clips on demand when you hover
a camera tile. The template details player performs the same preload-and-swap so
you begin watching instantly while the HD clip downloads in the background.

Hovering a tile for at least a third of a second now triggers the HD clip fetch.
Rushing across many tiles no longer spawns new renders for each one. If more
than eight tiles are visible or a tile is under 200&nbsp;px wide the dashboard
sticks with the low‑resolution `/last_video` preview.

When system metrics exceed safe thresholds the `/clip` endpoint now falls
back to `/last_video` immediately. The response includes an
`X-Degraded-Service: busy` header and the spinner switches to a dotted
pattern to indicate reduced quality.

If `/clip` hasn't finished rendering yet the server adds an
`X-Clip-Status: waiting` header. The braille glyph becomes a bouncing dot in the
corner so you know the HD version is still processing.
