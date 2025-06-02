# Documentation Overview

This folder contains all the user and developer guides for Glimpser.
If you're looking for the list of available documents, see [index.md](index.md).

- The Settings page now includes descriptive `title` attributes on form controls
  to improve accessibility.
- The navigation bar's Settings link now uses a single descriptive `title` attribute.
- Unit tests now cover configuration retrieval and Chrome debug port detection.
- Retention policy file sorting is also verified by tests.
- Screenshot utility functions now have dedicated unit tests.
- Shutdown helpers and port checks are validated by new tests.
- LLM response count now reads the number of stored entries in `data/llm_usage.json`.
- Footer now displays the package version from installed metadata.
- Footer version link shows a warning icon when a newer release is available.
- The VERSION setting now syncs with the installed package version on startup.
- Template and live views now show camera metadata, and PNG streams stop when switching sources.
- Templates are rescheduled when saved to apply the new settings.
- The front page 'Play All' button now works again after moving its script initialization to DOMContentLoaded.
- The live view page no longer shows a duplicate navigation header.
- The Discover page link now appears as a magnifying glass icon for consistent navigation.
- Group and All cameras now bypass offline checks when loading feeds.
- Live view groups stream each camera sequentially with the speed slider and hide the slider for single cameras.
- The "All" camera PNG stream now refreshes automatically.
- HTML templates are tested for image `alt` text and required form fields.
- Template storage usage is now verified by unit tests.
- Prompt optimizer logic is now tested for screenshot handling and prompt restoration.
- Template and live views now provide links to open the monitored page directly.
- Template edit form now uses `.form-row` containers for aligned inputs.
- The Add Template form auto-fills the Groups field when a filter is selected.
- Help page now covers CLI usage, configuration pointers, and links back to the app.
- CSS files are now linted in CI using **stylelint**.
- UI now uses the Inter font for improved readability.
- Stylelint case rule is disabled for the Inter font variable.
- Navigation health indicator uses a dedicated CSS class.
- JavaScript is now split into modules for templates, video controls, and scheduler toggling.
- Navigation logic and form validation are now modules to keep templates concise.
- Core colors and fonts are defined via CSS variables.
- Navigation menus use a consistent accent color with smooth hover effects.
- Session cookies are now marked secure/HTTPOnly and expire after a configurable timeout.
- Player pages fade the navigation bar when the mouse is idle for a few seconds.
- Templates track capture failures and display a warning icon when screenshots fail.
- Keyboard shortcuts now allow play/pause, mute, and fullscreen toggling when watching live video.
