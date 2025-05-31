# Self-hosting Fonts

Glimpser uses the [Inter](https://rsms.me/inter/) font for a clean and modern look. To ensure the UI works without an internet connection, the application loads the font files from `app/static/fonts` if they are present.

Download `Inter-Regular.woff2` and `Inter-Bold.woff2` from the Inter project and place them in that directory before starting the app. If the files are missing, the UI will fall back to system fonts.
