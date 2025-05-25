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

### Changed
- Improved screenshot reliability
- Enhanced camera list UI and video player controls
- Updated package requirements and cleaned up imports

### Fixed
- Addressed Python build issues and string concatenation errors
- Fixed screenshot timeouts and setup script problems

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

[Unreleased]: https://github.com/KristopherKubicki/glimpser/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/KristopherKubicki/glimpser/releases/tag/v1.0.0
