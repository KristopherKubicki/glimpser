# Captions Live Update

The captions page can refresh without reloading the entire application. When automatic updates are enabled, new caption text appears as soon as it is generated.
When the **History** table on the Captions page is sorted by Timestamp in descending order, new summaries are automatically inserted at the top. The page checks `/captions_status` every 10&nbsp;seconds and only adds a row when a newer caption exists. Click the Timestamp header again to disable live updates.
