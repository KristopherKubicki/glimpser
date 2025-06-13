# Test Pattern Reference

The test pattern includes calibration checks for panel accuracy and HDR tone mapping.

- **11‑step grayscale gradient** with a continuous ramp and discrete 2 % patches.
- **Alternate backgrounds** around patches let near‑black and near‑white chips float.
- **Multi‑burst wedges** render vertical and horizontal bursts from 1 to 10 px.
- **Fine checkerboard** region highlights chroma and luma mis‑registration.
- **Concentric circles and cross‑hair** at 45 %, 30 % and 15 % radii verify geometry.
- **100 px grid** in faint grey helps detect overscan.
- **HDR specular targets** at 400, 1 000 and 4 000 nit simulate tone mapping.
- **Mid‑grey uniformity patch** reveals panel mura without blinding brightness.
- **Skin‑tone chip** around CIE ab ≈ (20, 15) confirms natural faces.
- **Synthwave sunrise** with a small horizon line and trees for visual flair.
- **Moon phase display** rises opposite the sun in a smaller arc.
- **Swatch Internet Time** (@beats) joins the stacked clocks for a fun extra.
- **Analog second hand** in the bullseye extends to the outer dots for easy reading.
- **Date overlay** appears on the left aligned with the standard clock.
- **Braille spinner** in the corner updates once per second during streaming.
- **Mini color bars** in the top-left align with a reduced checker patch and grayscale swatch.
- **Pulsing QR code** with the current time and build hash appears in the lower-right quadrant.

The pattern now also includes:

- **Full-width SMPTE bars** with a 100 % row above a 75 % row for vectorscope calibration.
- **Super-white and super-black patches** on the left and right edges.
- **Grayscale staircase** spanning the width under the bars.
- **Concentric zone plate** behind the bullseye to expose aliasing.
- **HDR metadata** (SMPTE ST 2086) embedded in each JPEG header for HDR auto-switching.
- **ST 2110-21 alignment hash** marking frames for packet timing tests.
