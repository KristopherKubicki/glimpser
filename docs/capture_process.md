# Capture Process and Flow in Glimpser

This document provides an overview of how the capture process works in the Glimpser project, including the capture flow and the various methods used for different types of content.

## Table of Contents

1. [Overview](#overview)
2. [Main Capture Function](#main-capture-function)
3. [Capture Flow](#capture-flow)
4. [Content-Specific Capture Methods](#content-specific-capture-methods)
5. [Browser-Based Capture](#browser-based-capture)
6. [Post-Processing](#post-processing)

## Overview

The Glimpser project uses a modular approach to capture content from various sources, including images, PDFs, video streams, and web pages. The capture process is designed to handle different types of content efficiently and provide consistent output.

## Main Capture Function

The main entry point for the capture process is the `capture_or_download` function in `app/utils/screenshots.py`. This function orchestrates the entire capture process by:

1. Parsing the input URL and checking if the host is reachable
2. Determining the content type
3. Choosing the appropriate capture method based on the content type and other parameters
4. Handling the capture process and any necessary post-processing

## Capture Flow

The general flow of the capture process is as follows:

1. **Input Validation**: Check if the provided name and template are valid.
2. **URL Parsing**: Extract the domain and port from the URL.
3. **Host Reachability Check**: Ensure the target host is reachable.
4. **Output Path Preparation**: Generate a unique output path for the captured content.
5. **Content Type Determination**: Analyze the URL and perform a HEAD request to determine the content type.
6. **Capture Method Selection**: Choose the appropriate capture method based on the content type and other parameters.
7. **Capture Execution**: Execute the selected capture method.
8. **Post-Processing**: Apply any necessary post-processing steps, such as adding timestamps or applying dark mode.
9. **Result Handling**: Return the success status of the capture process.

## Content-Specific Capture Methods

Glimpser uses different methods to capture various types of content:

1. **Images**: Direct download using the `download_image` function.
2. **PDFs**: Download and convert to image using the `download_pdf` function.
3. **Video Streams**: Capture a frame using `capture_frame_from_stream` or `capture_frame_with_ytdlp` for more complex video sources.
4. **Web Pages**: Use either a lightweight browser capture (`capture_screenshot_and_har_light`) or a full browser capture (`capture_screenshot_and_har`) depending on the complexity of the page and capture requirements.

## Browser-Based Capture

For web pages, Glimpser uses two main approaches:

1. **Lightweight Browser Capture**: Uses `wkhtmltoimage` for simple web pages without complex JavaScript or popup handling requirements.
2. **Full Browser Capture**: Uses Selenium with Chrome/Chromium for more complex web pages, supporting JavaScript execution, popup handling, and custom selectors.

The choice between these methods depends on factors such as:
- Presence of popups that need to be handled
- Need for JavaScript execution
- Requirement for stealth mode
- Presence of dedicated selectors for capturing specific elements

## Post-Processing

After capturing the content, Glimpser applies several post-processing steps:

1. **Background Removal**: Remove unnecessary background from captured images.
2. **Dark Mode**: Apply dark mode to the captured image if requested.
3. **Timestamp Addition**: Add a timestamp to the captured image for reference.
4. **Image Optimization**: Ensure the captured image is in the correct format and optimized for storage.

## Conclusion

The capture process in Glimpser is designed to be flexible and handle a wide variety of content types and capture scenarios. By using a modular approach and content-specific capture methods, Glimpser can efficiently capture and process content from various sources while maintaining consistency in the output.