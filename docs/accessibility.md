# UI Accessibility Improvements

The user interface now includes additional tooltips and descriptive alt text to improve accessibility:

- Navigation and login logos include descriptive `alt` attributes.
- The live feed image has both `alt` text and a tooltip.
- The footer Help link displays a tooltip describing its purpose.
- The navigation Settings link has a single descriptive `title` attribute.
- The Discover page icon also uses a descriptive `title` attribute.
- When a camera is offline, the player shows an overlay with a clear icon instead of replacing the controls.
- Deprecated `<center>` tags were removed from templates and replaced with CSS-based centering.
- Error pages, the status dashboard, and video players now include tooltips on buttons and metrics.
- A "skip to main content" link enables quick keyboard navigation.
- The base template uses a `<main>` element for semantic structure.
- Live video overlays use ARIA roles so screen readers announce status changes.
- Offline and error indicators now include `title` attributes so assistive
  technology can describe the icon meaning.
- Focus outlines appear when navigating via keyboard.
- The delete button text color now meets color contrast guidelines.
- The live player styles moved to `player.css` and the index page uses
  `<section>` elements for clearer structure.
