# Glimpser FAQ

This document answers frequently asked questions about using Glimpser.

## General Questions

### What is Glimpser?
Glimpser is a monitoring and summarization tool that captures screenshots or video streams, then produces concise captions and summaries using AI models.

### Where is data stored?
By default, data such as screenshots, videos, and summaries are stored inside the `data/` directory. You can change the paths using the configuration options described in the [Configuration Guide](configuration_guide.md).

### How do I learn what each control does in the web interface?
Hover your mouse over any control in the web interface to reveal a tooltip describing its function.

## Configuration

### How do I change the database location?
Set the `GLIMPSER_DATABASE_PATH` environment variable before starting the app. The default path is `data/glimpser.db`.

### How do I enable email notifications?
Ensure the `EMAIL_ENABLED` setting is set to `True` and configure the remaining email settings (SMTP server, username, password). These options can be adjusted from the web interface or the configuration file.

### How do I enable SMS alerts?
Set `TWILIO_SID`, `TWILIO_TOKEN`, and `TWILIO_NUMBER` in the configuration. When these values are present, Glimpser will send important alerts via text message as well as email.
### Why is the thumbnail size slider so narrow?
The width slider on the index page now scales with the browser window. If it appears cramped, try widening the window or adjust the CSS in `style.css` to suit your layout.

### Why is the live feed slightly cropped on small screens?
Older styles fixed the video container height with `overflow: hidden`, which could cut off controls on short displays. The container now allows scrolling so everything stays visible.


## Troubleshooting

### I'm unable to log in
Make sure you are using the correct credentials. If you forget your password, you can reset it through the recovery process on the login page.

### Where can I get more help?
If this FAQ doesn't answer your question, check the [Troubleshooting Guide](troubleshooting.md) or open an issue on GitHub.
