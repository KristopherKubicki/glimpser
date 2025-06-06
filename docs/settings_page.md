# Settings Page Overview

The **Settings** interface lets you manage configuration values stored in the database. Each field includes a tooltip that explains its purpose. A collapsible **Settings Reference** table lists every configuration option with detailed descriptions. Settings are organized into categories with navigation tabs just like the Captions page.

## Sections

- **Add New Setting** – quickly create additional key/value pairs.
- **Current Settings** – edit existing values or delete them. Tabs switch between setting groups and the **Management** tab holds backup and offline options.
- **Configuration Management** – backup, download, and upload the JSON configuration file.
- **Danger Mode** – update Chrome shortcuts with the required flags.
- **Offline Preview** – cached snapshots are automatically enabled.
- **Settings Reference** – expand the table to read explanations for each setting.
- **Column Search** – click a header to filter rows by that column.
- **Interface** – UI-related options like the navigation logo now live on their own tab.

Each row now includes an **Explanation** column so you can read a short
description without opening the reference table. Boolean values are
displayed as toggle switches to avoid typing errors. Values such as `true`
or `False` (any case) are recognized automatically.

### Dynamic Feedback

Focusing any input field shows a tooltip on screen with a description pulled from the database. When adding a new setting, errors display inline so issues can be fixed before submitting the form.

### Selectable Options

Common settings like `HOST`, `LANG`, `LOG_LEVEL`, and `TZ` now use a single autocomplete field. Typing shows suggestions for common values, but any text can be entered. The `PORT` field enforces non‑privileged ports (1024–65535) to avoid permission errors.
