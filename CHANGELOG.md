# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Bulk caption management with TSV import and export
- Configuration backup and restore
- System status and log viewing pages
- Real-time log streaming with improved filtering
- Console clearing command
- Google Cast support
- Integration with Blue Iris, Home Assistant and Hubitat
- Custom video controls including Play All/Stop All
- Automatic group loading for cameras
- API discovery and paginated log view
- LLM summary generation with email alerts
- Capture time tracking for templates
- FFprobe path configuration
- Live video streaming endpoint `/live_video`
- Python 3.11 compatibility
- mDNS/Zeroconf camera discovery

### Changed
- Improved screenshot reliability
- Enhanced camera list UI and video player controls
- Updated package requirements and cleaned up imports

### Fixed
- Fixed missing dark mode application when downloading images
- Fixed screenshot timeouts and setup script problems
- Offline cameras now display an overlay and keep the camera selector usable

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
- N/A

[Unreleased]: https://github.com/KristopherKubicki/glimpser/compare/v0.2.4...HEAD
[0.2.4]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.4
[0.2.3]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.3
[0.2.2]: https://github.com/KristopherKubicki/glimpser/releases/tag/v0.2.2
[1.0.0]: https://github.com/KristopherKubicki/glimpser/releases/tag/v1.0.0
