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
- LLM response count is now verified by a unit test that patches `random.randint`.
- Footer now displays the package version from installed metadata.
- Template and live views now show camera metadata, and PNG streams stop when switching sources.
- Templates are rescheduled when saved to apply the new settings.
- The front page 'Play All' button now works again after moving its script initialization to DOMContentLoaded.
- The live view page no longer shows a duplicate navigation header.
- The Discover page link now appears as a magnifying glass icon for consistent navigation.
- Group and All cameras now bypass offline checks when loading feeds.
- The "All" camera PNG stream now refreshes automatically.
- HTML templates are tested for image `alt` text and required form fields.
- Template storage usage is now verified by unit tests.
- Prompt optimizer logic is now tested for screenshot handling and prompt restoration.
- Template and live views now provide links to open the monitored page directly.
- Template edit form now uses `.form-row` containers for aligned inputs.
- The Add Template form auto-fills the Groups field when a filter is selected.
- Help page now covers CLI usage, configuration pointers, and links back to the app.
- CSS files are now linted in CI using **stylelint**.
