# Getting Started with Glimpser

This guide will walk you through the process of setting up Glimpser and running your first monitoring task.

## Prerequisites

- Python 3.8 to 3.12
- Git (for cloning the repository)

## Installation

1. Clone the Glimpser repository:
   ```
   git clone https://github.com/KristopherKubicki/glimpser.git
   cd glimpser
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the application:
   ```
   python3 main.py
   ```

4. Follow the prompts to create a secret key and initialize the local SQLite database.

5. Open your web browser and navigate to `http://127.0.0.1:8082` to complete the setup.

   **Note:** Glimpser sets the `SESSION_COOKIE_SECURE` flag by default, so
   browsers only send the login cookie over HTTPS. If you're running locally
   without HTTPS, set `SESSION_COOKIE_SECURE=False` in your environment before
   starting the app to allow non-HTTPS logins. See the
   [Configuration Guide](configuration_guide.md#user-credentials) for details.

## Your First Monitoring Task

1. Log in to the Glimpser web interface.

2. When no templates exist, the **Add Camera** form automatically opens on the **Settings → Add** tab.
   Otherwise, navigate to that tab to add a new source.

3. Choose a data source type (e.g., camera, dashboard, or video stream).

4. Configure the source settings (URL, refresh rate, etc.).

5. Save the source configuration.

6. Go to the "Monitoring" section to view your live data feed.

7. On the **Live** page, select your camera. MJPG is selected by default, but choose **Live Video** from the
   "Video Source" dropdown for direct streaming.

8. Explore the auto-generated captions and summaries.
9. Use the **Suggest Prompt** button on a template's detail page to have the system propose better caption text.
10. Visit the **Captions** page to review and manage prompts. The view now has three tabs: **Prompts** (camera grid with filters), **History** (recent captions table), and **Bulk Tools** for TSV updates. The History tab is always expanded and provides search and date range filters. Use the search box in the Prompts tab to quickly find a camera. KPI and caption columns can be sorted by clicking their headers, which display a ↕ icon. Rows show relative timestamps, and thumbnails appear dimmed until hovered. A width slider resizes thumbnails and adjusts their height, capping them at 1080&nbsp;px.

## Next Steps

- Explore the [Recommendations](recommendations.md) document for advanced use cases.
- Check out the [Configuration Guide](configuration_guide.md) to customize Glimpser for your needs.
- Join our [community forum](#) to connect with other Glimpser users and get support.

## Offline Help

After you visit the `/help` route while online, the help page is stored locally. You can then access `/help` anytime for instructions on adding templates, managing captures, and troubleshooting, even without an internet connection.

Happy monitoring!
