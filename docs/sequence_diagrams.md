# Sequence Diagrams

This page illustrates a few key flows within Glimpser. Each diagram is provided
as an SVG so it renders cleanly at any size.

## Application Startup

![Startup Sequence](diagrams/startup_sequence.svg)

The diagram shows how the Flask application initializes, starts the scheduler,
and launches the watchdog thread before returning control to the caller.

## Capture Flow

![Capture Flow](diagrams/capture_flow.svg)

Scheduler jobs trigger `capture_or_download`, which writes screenshots to disk
and stores references in the database. The summarizer updates the text summary
for each template.

## Login Flow

![Login Flow](diagrams/login_flow.svg)

A standard login request verifies the credentials against the database and, on
success, stores the user ID in the session before redirecting to the dashboard.
