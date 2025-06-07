# Jog-Shuttle Control

The live viewer offers a jog-shuttle widget for cameras that support video playback. Drag within the circle to scrub forward or backward. The farther you drag from the center the faster playback runs (1x, 2x, 4x and so on). Crossing the center reverses direction. Releasing the control pauses and snaps back to neutral.

The jog-shuttle appears only when an individual camera is selected and the **MP4** or **Loop** source is active. Other sources like MJPG or live streams are not seekable, so the control is hidden.

Input events are throttled per animation frame for smooth scrubbing.
