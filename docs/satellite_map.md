# Satellite Map Utility

The `satellite_map` helper renders a basic orbital ground track using Two-Line
Element (TLE) data. Call `generate_satellite_map()` to obtain a `PIL.Image`
showing latitude/longitude grid lines with the satellite's predicted path for
the next ninety minutes.

Use `save_satellite_map()` to write the image to disk. The frames produced by
this utility can feed a future `/satellite.mjpg` endpoint.
