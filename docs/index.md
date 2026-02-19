# Glimpser Documentation

Glimpser monitors cameras and video streams, applying AI to summarize important changes and trigger alerts. The documentation explains how to install, configure, and extend the platform. Use the sections below to jump to topics of interest.

## Getting Started

- [Getting Started](getting_started.md)
- [Installation Guide](installation.md)
- [In-App Onboarding](onboarding.md)
- [Command Line Reference](command_line.md)
- [Integration Guide](integration_guide.md)
- [FAQ](faq.md)

## Feature Guides

- [Capture Process](capture_process.md)
- [Camera Discovery](camera_discovery.md)
- [Video Archiver](video_archiver.md)
- [Video and Image Endpoints](video_image_endpoints.md)
- [Live View Scrubbing](live_scrub.md)
- [Dashboard Live Button](live_all.md)
- [Google Home WEB_RTC Support](google_home_webrtc.md)
- [Search Bar Autocomplete](search_autocomplete.md)
- [Jog-Shuttle Control](jog_shuttle.md)
- [Web Notifications](web_notifications.md)
- [UI Accessibility Improvements](accessibility.md)

## Administration

- [Configuration Guide](configuration_guide.md)
- [Configuration Management](config_management.md)
- [System Monitoring and Logs](system_monitoring.md)
- [Docker Build Verification](docker_build.md)
- [Danger Mode](danger_mode.md)
- [Nginx HTTP/2 Push](nginx_http2_push.md)
- [Offline Preview](offline_preview.md)

## Developer Resources

- [Developer Guide](developer_guide.md)
- [Testing and Coverage](testing.md)
- [Release Workflow](release_workflow.md)
- [Docs Build Workflow](docs_build.md)
- [Pylint Checks](pylint_checks.md)
- [Dependency Review](dependency_review.md)
- [Continuous Integration Checks](ci_checks.md)
- [Staged GitHub Flow](staged_github_flow.md)
- [CodeQL Security Scanning](codeql.md)
- [OpenSSF Scorecard](scorecard.md)

Additional topics such as [Cost Tracking](cost_tracking.md), [Captions Chatbot](chatbot.md), [Recommendations](recommendations.md) and [Settings Page Overview](settings_page.md) are covered in dedicated guides.

## Dashboard Time

The main dashboard now displays the current time in the lower right corner. Hover over the time to view the full ISO 8601 timestamp.

Thumbnails also now show the last capture time in a compact "5m ago" style, matching the tables on the Captions page. The Live View page displays the time of the latest frame in the lower-right corner using the same format. Timestamp parsing was improved so times display correctly across time zones instead of always showing "just now".
