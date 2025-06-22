# Dashboard Border Legend

The index page shows each camera tile with a colored border.
Border thickness is now slimmer (2&nbsp;px) so the legend key no longer
dominates the layout. The legend now sits next to the **Play All** button on the
dashboard rather than occupying its own row. A single legend element is rendered
to avoid duplication when the page loads.

- **Accent border** – blue for recent captures. The color intensity fades by half after one minute,
  again after ten minutes, and so on.
- **Gray border** – indicates the most recent capture attempt failed. The gray border fades using the
  same logarithmic scale. A successful capture clears the error state.
