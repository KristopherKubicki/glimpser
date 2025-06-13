# Dashboard Border Legend

The index page shows each camera tile with a colored border.
Border thickness is now slimmer (2&nbsp;px) so the legend key no longer
dominates the layout. The legend now sits next to the **Play All** button on the
dashboard rather than occupying its own row. A single legend element is rendered
using a template macro to avoid duplication when the page loads. The same legend
also appears on the **Captions** and **Group** pages.

- **Accent border** – blue for recent captures. The color intensity fades by half after one minute,
  again after ten minutes, and so on.
- **Red border** – indicates the most recent capture attempt failed. The red border fades using the
  same logarithmic scale. A successful capture clears the error state.

Search, width slider and legend controls now start collapsed in a dropdown to keep the dashboard uncluttered.
The dropdown closes automatically after a few seconds without mouse or scroll activity.
On desktop screens the **Controls** button itself stays hidden until you move the
mouse, fading out again when idle just like the toolbar on template pages.

Clicking **Recent** or **Error** in the legend now filters the dashboard to only show
those cameras. The legend entries gray out when no tiles match.
