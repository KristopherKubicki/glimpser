# Glimpser FAQ

This document answers frequently asked questions about using Glimpser.

## General Questions

### What is Glimpser?
Glimpser is a monitoring and summarization tool that captures screenshots or video streams, then produces concise captions and summaries using AI models.

### Where is data stored?
By default, data such as screenshots, videos, and summaries are stored inside the `data/` directory. You can change the paths using the configuration options described in the [Configuration Guide](configuration_guide.md).

## Configuration

### How do I change the database location?
Set the `GLIMPSER_DATABASE_PATH` environment variable before starting the app. The default path is `data/glimpser.db`.

### How do I enable email notifications?
Ensure the `EMAIL_ENABLED` setting is set to `True` and configure the remaining email settings (SMTP server, username, password). These options can be adjusted from the web interface or the configuration file.

## Troubleshooting

### I'm unable to log in
Make sure you are using the correct credentials. If you forget your password, you can reset it through the recovery process on the login page.

### Where can I get more help?
If this FAQ doesn't answer your question, check the [Troubleshooting Guide](troubleshooting.md) or open an issue on GitHub.
