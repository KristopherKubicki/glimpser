# Settings Page Overview

The **Settings** interface lets you manage configuration values stored in the database. Each field includes a tooltip that explains its purpose. A collapsible **Settings Reference** table lists every configuration option with detailed descriptions. Settings are organized into categories with navigation tabs just like the Captions page.

## Sections

- **Add New Setting** – quickly create additional key/value pairs.
- **Current Settings** – edit existing values. Delete actions appear when advanced options are enabled using the toggle under the **Management** tab. Tabs switch between setting groups and the Management tab holds backup and offline options.
- **Configuration Management** – backup, download, and upload the JSON configuration file.
- **Credentials & Management** – buttons are organized into cards for a cleaner layout.
- **Danger Mode** – shows the detected browser path, Chrome version, and the first shortcut found. Green and red dots indicate if shortcuts are patched and if the debugging port is open. A link beside the heading opens the [Danger Mode documentation](danger_mode.md). You can also update Chrome shortcuts from here.
- **Offline Preview** – cached snapshots are automatically enabled.
- **Settings Reference** – expand the table to read explanations for each setting.
- **Column Search** – click a header to filter rows by that column.
- **Tab headers removed** – the active tab is highlighted, freeing space.
- **Unsaved Changes Indicator** – a small alert icon appears next to the Save
  Changes button when edits haven't been saved.
- **System Status** – view CPU, memory, disk usage, and live logs.
- **Certain tabs start collapsed** – Capture, Credentials & Management, and
  Integrations & Other appear collapsed until expanded.

All form elements now use unique IDs across tabs to avoid browser warnings.

- **File Location Checks** – paths in the Capture tab are validated and show a
  small progress bar indicating remaining disk space.
- **Interface** – UI-related options like the navigation logo now live on their own tab.

Hover over a setting name to see a tooltip with its explanation.
Boolean values are displayed as toggle switches to avoid typing errors.

### Dynamic Feedback

Focusing any input field shows a tooltip on screen with a description pulled from the database. When adding a new setting, errors display inline so issues can be fixed before submitting the form.

### Selectable Options

Common settings like `HOST`, `LANG`, `LOG_LEVEL`, and `TZ` now use searchable dropdowns populated with sensible defaults. Custom values may still be entered but `TZ` choices are validated against the system time zone database. The `PORT` field only accepts ports the current user can bind to, preventing permission errors.
Numeric settings such as `MAX_WORKERS` or `EMAIL_SMTP_PORT` use number inputs so invalid characters cannot be entered. `MAX_WORKERS` is capped at twice the available CPU count. Email fields validate that addresses are well formed before submission.

### Validation

Values submitted through the form are validated on the server. Numeric fields like `PORT` or `MAX_WORKERS` must contain valid integers within the accepted range. Boolean options are normalized to `True` or `False` so unexpected text does not pollute the database.
