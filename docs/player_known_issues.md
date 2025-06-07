# Player Known Issues

Below are five player-focused bugs and design flaws frequently reported by users. Each paragraph can be dropped directly into an issue tracker.

## Crop-left scaling bug
Every `<video>` inside a `.templateDiv` is `position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain;`, but the parent `.templateDiv` never constrains its own aspect ratio. When the browser narrows the tile, the player still renders the full-resolution frame, then clips whatever exceeds the div’s fixed height—so the user only sees the upper-left quadrant instead of a letter-boxed image. Wrap the video in a `position:relative` container with `aspect-ratio:` or padding-top hack, or (simplest) switch the parent to `display:flex` + `align-items:center; justify-content:center;` so the browser centers and scales without cropping. Users will finally get a true “shrink-to-fit” view, and mobile layouts stop exploding.

## Mouse-drag shuttle floods seek events
The jog-shuttle slider fires `mousemove` on every pixel change, and the handler calls both `video.currentTime = …` and `video.playbackRate = …` immediately. At normal mouse speeds that’s 300–500 seeks per second, hammering the decoder and causing visible frame stalls. Debounce or `requestAnimationFrame`-throttle the update loop (e.g., only apply the last value per frame) and use `video.pause()` while scrubbing, then resume with the final rate. One-line tweak but it turns jerky scrubs into buttery-smooth shuttling.

## Duplicate "timeupdate" listeners → memory leak & HUD jitter
Each time the player reloads a source or switches cameras it calls `video.addEventListener('timeupdate', updateHud)`, but it never removes prior listeners. After a few reloads you end up with multiple identical callbacks firing in parallel: the progress bar jumps, the timestamp stutters, and detached closures keep old DOM references alive. Before attaching, run `video.removeEventListener('timeupdate', updateHud)` (or use `once:true` in modern browsers). This prevents both UI jitter and a slow memory creep that’s obvious during long monitoring sessions.

## Poster frame is full-resolution → huge placeholder on mobile
When a template lacks an explicit thumbnail, the frontend grabs the most recent JPEG frame and feeds it straight to the `poster` attribute. Those frames are typically 1920×1080+ uncompressed, so mobile users download 3–5 MB before the first byte of video. Generate a 20 kB 480-wide preview in the backend (e.g. `ffmpeg -vf scale=480:-2`) or client-side downscale to canvas once, cache, and reuse. Page-load size drops by an order of magnitude and Lighthouse “Largest Contentful Paint” finally turns green.

## Background tab still burns CPU
The player runs a `setInterval(drawOverlay, 33)` even when the tab is hidden, which keeps decoding frames and updating the canvas at ~30 fps while nobody is looking. Tie the loop to `document.visibilityState` (`pause()` + `cancelAnimationFrame()` on hide, restart on show). Laptop fans calm down, battery life improves, and server bandwidth drops whenever users switch away from the tab.

