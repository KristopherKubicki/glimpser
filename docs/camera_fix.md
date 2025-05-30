# Camera Fix Suggestions

The `/suggest_fix/<template>` route validates a template's URL and XPath settings. It tries to load the configured page with `requests` and checks for the provided XPaths. If loading fails, Glimpser automatically runs camera discovery to look for matching cameras.

The response includes whether the URL loaded correctly, which XPaths were found, and a list of suggested replacement URLs discovered on the network.

Use the "Suggest Fix" button on the template details page to call this endpoint and view suggestions.
