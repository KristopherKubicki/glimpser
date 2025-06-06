# Glimpser Documentation

Glimpser is a monitoring platform that captures images and video streams, using advanced image processing and AI to summarize and alert on changes. This page links to the guides and references available in the repository.

- [API Documentation](api_documentation.md)
- [Capture Process](capture_process.md)
- [Configuration Guide](configuration_guide.md)
- [Command Line Reference](command_line.md)
- [Video Archiver](video_archiver.md)
- [Live All Playback](live_all.md)
- [Live View Scrubbing](live_scrub.md)
- [Jog-Shuttle Control](jog_shuttle.md)
- [Developer Guide](developer_guide.md)
- [Testing and Coverage](testing.md)
- [Release Workflow](release_workflow.md)
- [Docker Build Verification](docker_build.md)
- [CodeQL Security Scanning](codeql.md)
- [Continuous Integration Checks](ci_checks.md)
- [System Monitoring and Logs](system_monitoring.md)
- [Danger Mode](danger_mode.md)
- [FAQ](faq.md)
- [Getting Started](getting_started.md)
- [In-App Onboarding](onboarding.md)
- [Installation Guide](installation.md)
- [Integration Guide](integration_guide.md)
- [Camera Discovery](camera_discovery.md)
- [Help Page Overview](help_page.md)
- [Camera Fix Suggestions](camera_fix.md)
- [HTTP Callback Guide](http_callbacks.md)
- [MCP Integration](mcp_integration.md)
- [Recommendations](recommendations.md)
- [Troubleshooting](troubleshooting.md)
- [Startup Tips](startup_tips.md)
- [Architecture Overview](architecture_overview.md)
- [UI Accessibility Improvements](accessibility.md)
- [Dark Mode Support](dark_mode.md)
- [UI Component Guide](style_guide.md)
- [UI Design Guidelines](design_guidelines.md)
- [Dashboard Time Display](#dashboard-time)
- [Dashboard Border Legend](border_legend.md)
- [LLM Cost Tracking](cost_tracking.md)
- [Captions Chatbot](chatbot.md)
- [UI and Navigation Tooltips](tooltips.md)
- [Settings Page Overview](settings_page.md)
- [Configuration Management](config_management.md)
- [Offline Preview](offline_preview.md)
- [Web Notifications](web_notifications.md)
- [Nginx HTTP/2 Push](nginx_http2_push.md)
- [API Resilience](api_resilience.md)
- [OpenSSF Scorecard](scorecard.md)

## Dashboard Time

The main dashboard now displays the current time in the lower right corner. Hover over the time to view the full ISO 8601 timestamp.

Thumbnails also now show the last capture time in a human readable
"X ago" format, matching the tables on the Captions page.
The Live View page displays the time of the latest frame in the
lower-right corner using the same format. Timestamp parsing was improved so
times display correctly across time zones instead of always showing
"just now".
