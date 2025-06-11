# Braille Loading Spinner

Videos initially display the quick `/last_video` clip while the full `/clip` file loads.
A small braille spinner appears over the thumbnail until the HD video is ready.
This keeps pages responsive and provides visual feedback that higher quality
footage is on the way. The template details player now performs the same
preload-and-swap so you begin watching instantly while the HD clip downloads in
the background.

When system metrics exceed safe thresholds the `/clip` endpoint now falls
back to `/last_video` immediately. The response includes an
`X-Degraded-Service: busy` header and the spinner switches to a dotted
pattern to indicate reduced quality.

If `/clip` hasn't finished rendering yet the server adds an
`X-Clip-Status: waiting` header. The braille glyph becomes a bouncing dot in the
corner so you know the HD version is still processing.
