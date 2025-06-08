# Configuration Management

Glimpser allows you to export and restore configuration data from the web interface. This feature is useful when migrating installs or when you want a backup copy of all camera and setting entries.

## Downloading the Configuration

1. Open the **Settings** page from the navigation bar.
2. Switch to the **Credentials & Management** tab.
3. Click **Download Configuration** to save the current settings as a JSON backup.
   A new backup is created automatically before the file is served.

The downloaded file contains every setting and camera template defined in the database.

## Uploading the Configuration

1. From the same **Credentials & Management** tab, choose a previously saved JSON file.
2. Click **Upload Configuration** and confirm the restore action.

All existing settings and templates will be replaced by the contents of the file.

## Captions TSV Import/Export

The **Captions** page includes bulk tools for exporting and importing prompts.

1. Go to **Captions** → **Bulk Tools**.
2. Click **Download Captions as TSV** to get a tab-separated file of all prompts.
3. Edit the TSV in a spreadsheet application.
4. Upload the updated file using **Upload TSV**.

These steps make it easy to manage caption text outside the interface.
