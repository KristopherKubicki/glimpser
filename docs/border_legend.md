# Dashboard Border Legend

The index page shows each camera tile with a subtle 1&nbsp;px border. Recent and
failed captures display an inset 2&nbsp;px glow instead of a thick outline. This
keeps the layout crisp while still conveying state. The legend now sits next to
the **Play All** button on the dashboard rather than occupying its own row. A
single legend element is rendered to avoid duplication when the page loads.

- **Accent border** – blue for recent captures. The color intensity fades by half after one minute,
  again after ten minutes, and so on.
- **Red border** – indicates the most recent capture attempt failed. The red border fades using the
  same logarithmic scale. A successful capture clears the error state.
