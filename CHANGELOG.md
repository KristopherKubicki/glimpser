# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Bulk caption management with TSV import and export
- Configuration backup and restore
- System status and log viewing pages
- Feed dashboard on the `/status` page summarizing camera health
- Real-time log streaming with improved filtering
- Console clearing command
- Google Cast support
- Integration with Blue Iris, Home Assistant and Hubitat
- Custom video controls including Play All/Pause All
- Automatic group loading for cameras
- Navigation dropdown now includes an "all" group and per-group camera menu
- Live view tooltip refreshes with the latest caption
- Add Template form auto-fills selected group
- API discovery and paginated log view
- LLM summary generation with email alerts
- Capture time tracking for templates
- FFprobe path configuration
- Live video streaming endpoint `/live_video`
- Python 3.11 compatibility
- Python 3.12 compatibility
- Python 3.13 compatibility
- mDNS/Zeroconf camera discovery
- MAC vendor lookup now consults local databases and an online API
- Footer warns when a newer release is available
- Stream error overlay distinguishes network and unsupported format errors
- Sortable KPI table on captions page with filtering
- Escher-inspired geometric test pattern generator
- `/test_pattern.mjpg` accepts `pattern=geometric` to view the new style

### Changed

- Improved screenshot reliability
- Enhanced camera list UI and video player controls
- Updated package requirements and cleaned up imports
- Added CPU builds of JAX 0.6.1 and Flax 0.2.0
- Bumped scikit-image to 0.25.0
- Bumped numpy to 1.26.0
- Removed nodriver and its screenshot helper
- Updated default VERSION to 0.2.7 for footer display
- The footer name now links to https://glimpser.net
- Bulk tools menu is expanded by default on the captions page
- Enumerated settings use a single autocomplete field instead of a dropdown and separate text box
- Live video retries now use exponential backoff to reduce repeated ffmpeg errors
- Template toolbar now anchors to the lower left of detail pages
- Image thumbnails show captions in their tooltips
- Dashboard tiles now use the `/clip` endpoint to loop the last two minutes of footage

### Fixed

- Addressed Python build issues and string concatenation errors
- Fixed screenshot timeouts and setup script problems
- Offline cameras now display an overlay and keep the camera selector usable
- `download_image` now reuses cached HTTP status codes to reduce retry overhead
- Fixed unclosed `.form-error` block in `style.css` causing CSS lint failures
- Timestamp and caption overlays now align correctly with their tinted
  backgrounds
- Repeated stream errors on the `/live` page are now throttled to prevent
  frequent popups.
- Loop playback no longer logs "NotAllowedError" when the browser blocks
  auto-play.
- Fixed a crash on the login page caused by missing clock elements in `nav.js`.
- Removed a duplicate form on the settings page that caused repeated element IDs
- Prevented undefined camera requests from returning 404 errors when switching
  live sources.
- Build details are hidden on small screens to avoid clutter.
- Sanitized log messages in the UI to prevent XSS vulnerabilities

## [0.2.7] - 2025-06-02

### Changed

- Bumped package version in setup.py to 0.2.7.

## [0.2.6] - 2025-06-01

### Changed

- Bumped package version in setup.py to 0.2.6.

## [0.2.5] - 2025-05-31

### Changed

- Bumped package version in setup.py to 0.2.5.

## [0.2.4] - 2025-05-28

### Changed

- Bumped package version in setup.py to 0.2.4.

## [0.2.3] - 2025-05-27

### Changed

- Bumped package version in setup.py to 0.2.3.

## [0.2.2] - 2025-05-26

### Changed

- Bumped package version in setup.py to 0.2.2.

## [1.0.0] - 2023-06-15

### Added

- Initial release of Glimpser
- Real-time monitoring capabilities
- Image processing and motion detection
- AI integration for captioning and summarization
- Customizable configuration through web interface
- Data retention policies

### Changed

- N/A

### Fixed

- Live video errors now fall back to the last screenshot so the live view never
  appears blank.

[Unreleased]: https://github.com/KristopherKubicki/glimpser/compare/v0.2.7...HEAD
[0.2.7]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.7
[0.2.6]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.6
[0.2.5]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.5
[0.2.4]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.4
[0.2.3]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.3
[0.2.2]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.2
[1.0.0]: https://github.com/KristopherKubicki/glimpser/releases/tag/v1.0.0
