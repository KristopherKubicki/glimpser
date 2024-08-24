def capture_frame_from_stream(
    url, output_path, num_frames=3, timeout=30, name="unknown", invert=False
):
    """Use ffmpeg to capture multiple frames from a video stream and save the last one."""
    if not is_ffmpeg_available():
        logging.error("ffmpeg is not available. Frame capture skipped.")
        return False

    with tempfile.TemporaryDirectory() as tmpdirname:  # todo make sure this gets dleted
        # Capture multiple frames into the temporary directory
        temp_output_pattern = os.path.join(tmpdirname, "frame_%03d.png")
        command = [
            "ffmpeg",
            "-hide_banner",
            #'-hwaccel', 'auto',
        ]

        probe_size = "5M"
        if "http:" in url or "https:" in url:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            command.extend(["-headers", "User-Agent: %s\r\n" % UA])
            command.extend(["-headers", f"referer: {base_url}\r\n"])
            command.extend(["-headers", f"origin: {base_url}\r\n"])
            command.extend(["-seekable", "0"])
            # command.extend(['-timeout', str(timeout-1)])  # not sure why, but this causes us a lot of issues, dont set a timetout
            probe_size = "5M"
        elif "rtsp:" in url:
            command.extend(["-rtsp_transport", "tcp"])
            probe_size = "10M"
            if "/streaming/" in url.lower():  # alittle bit of a hack
                command.extend(["-c:v", "h264"])
                command.extend(["-r", "1"])
                probe_size = "20M"
        else:
            probe_size = "20M"

        # todo: make this configurable instead
        command.extend(["-analyzeduration", probe_size])
        command.extend(["-probesize", probe_size])
        command.extend(
            [
                "-use_wallclock_as_timestamps",
                "1",
                #'-ec', '15',
                "-threads",
                "1",
                "-skip_frame",
                "nokey",
                "-sn",
                "-an",
                #'-err_detect','aggressive',
                "-i",
                url,  # Input stream URL
                "-movflags",
                "+faststart",
                "-pix_fmt",
                "rgb24",
                "-frames:v",
                str(num_frames),  # Capture 'num_frames' frames
                "-fflags",
                "+igndts+ignidx+genpts+fastseek+discardcorrupt",
                "-q:v",
                "0",  # Output quality (lower is better)
                #'-b:v', '50000000',               # Output quality (lower is better)
                "-f",
                "image2",  # Force image2 muxer
                temp_output_pattern,  # Temporary output file pattern
            ]
        )

        try:
            try:
                subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=17,
                )  # wanring hardcoded
                # print("mmm", ' '.join(command))
                # subprocess.run(command, check=True, timeout=timeout) # wanring hardcoded
            except Exception:
                # print("<<naye timeout...", e)
                pass

            # Sort the captured frames by size and take the last one
            frames = sorted(
                os.listdir(tmpdirname),
                key=lambda x: os.path.getsize(os.path.join(tmpdirname, x)),
            )
            if frames:
                last_frame_path = os.path.join(tmpdirname, frames[-1])
                # Move the last frame to the output path
                shutil.move(last_frame_path, output_path)
                if os.path.exists(output_path):
                    add_timestamp(output_path, name=name, invert=invert)
                    logging.info(f"Successfully captured frame from stream {url}")
                    return True
            else:
                logging.error(f"No frames captured from stream {url}")
        except Exception as e:
            logging.error(f"Error capturing frames from stream: {e}")

    logging.error(f"Error capturing frame with ffmpeg: {url}")
    return False