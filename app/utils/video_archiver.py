def compile_to_video(camera_path, video_path):
    if not is_ffmpeg_available():
        logging.error("ffmpeg is not available. Video compilation skipped.")
        return False

    os.makedirs(video_path, exist_ok=True)
    os.makedirs(camera_path, exist_ok=True)

    if not os.path.isdir(video_path):
        return False
    if not os.path.isdir(camera_path):
        return False

    in_process_video = os.path.join(video_path, "in_process.mp4")

    # Check if there is an "in-process" video and its size
    # TODO: check the creation_time and if it exceeds the alotment, then alos roll over
    if os.path.isfile(in_process_video):
        file_size_exceeded = (
            os.path.getsize(in_process_video) > MAX_IN_PROCESS_VIDEO_SIZE
        )
        file_age_exceeded = (
            datetime.datetime.utcnow()
            - datetime.datetime.fromtimestamp(os.path.getctime(in_process_video))
        ).total_seconds() > MAX_COMPRESSED_VIDEO_AGE * 60 * 60 * 24 * 7

        # condsider when the length is 2x300 frames as well.  so we always have perfect overlap at 2x

        if file_size_exceeded or file_age_exceeded:
            # Rename the "in-process" video to a "final" video with a timestamp
            final_video_name = f"final_{int(os.path.getmtime(in_process_video))}.mp4"
            # TODO: should we optimize the timing better?
            final_video_path = os.path.join(video_path, final_video_name)
            os.rename(in_process_video, final_video_path)
            # print(f'Video finalized: {final_video_path}')
            # this is going to generate overlapping segments, which is OK for now .

    # Get the modification time of the in-process video
    video_mod_time = (
        os.path.getmtime(in_process_video) if os.path.exists(in_process_video) else 0
    )

    ldur = 0
    if os.path.exists(in_process_video):
        ldur = get_video_duration(in_process_video)
        if (
            ldur < 10 and time.time() - video_mod_time > 60 * 60
        ):  # could be a waste of 300 frames...
            # print("  skipping ", in_process_video, ldur, time.time() - video_mod_time)
            video_mod_time = 0
            # go bigger...

    if os.path.exists(in_process_video) and ldur >= int(300 / 25 * 2):  # rotate!
        # Rename the "in-process" video to a "final" video with a timestamp
        final_video_name = f"final_{int(os.path.getmtime(in_process_video))}.mp4"
        # TODO: should we optimize the timing better?
        final_video_path = os.path.join(video_path, final_video_name)
        os.rename(in_process_video, final_video_path)
        # we should finalize at the END of the encode , right?
        # print(f'Video finalized: {final_video_path}')  #log instead
        # this is going to generate overlapping segments, which is OK for now .

    # Filter the list of image files to include only those that are newer than the video
    new_files = [
        f
        for f in glob.glob(camera_path + "/*.png")
        if os.path.getctime(f) > video_mod_time
    ]
    new_files = sorted(new_files)

    if len(new_files) > 0:
        # Create a temporary file with the list of new frames
        lcount = 0
        temp_file_path = None
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            for file in new_files[-300:]:  # keep it short for now
                if os.path.getsize(os.path.abspath(file)) > 10 and "_2" in file:
                    temp_file.write(f"file '{os.path.abspath(file)}'\n")
                    lcount += 1
            temp_file_path = temp_file.name
        if lcount == 0:
            # nothing to do
            os.remove(temp_file_path)
            return
        if temp_file_path is None:
            return  # should not be possible

        # Create a temporary video with the new frames
        temp_video = os.path.join(video_path, "in_process.tmp.mp4")

        create_command = [
            "ffmpeg",
            "-threads",
            "5",
            "-f",
            "concat",
            "-r",
            "25",  # for some reason the standard for png?
            "-c:v",
            "png",
            "-use_wallclock_as_timestamps",
            "1",
            "-err_detect",
            "ignore_err",
            "-fflags",
            "+igndts+ignidx+genpts+fastseek+discardcorrupt",
            "-copyts",
            "-start_at_zero",
            "-safe",
            "0",
            "-i",
            os.path.abspath(temp_file_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            "-movflags",
            "+faststart",
        ]
        create_command.extend(
            ["-metadata", "creation_time=%sZ" % datetime.datetime.utcnow()]
        )
        create_command.extend(["-metadata", "encoded_by=%s" % NAME])
        create_command.extend(["-metadata", "version=%s" % VERSION])
        create_command.extend(
            ["-y", os.path.abspath(temp_video)]
        )  # Overwrite if exists

        try:
            # print("CMD", lcount, ' '.join(create_command))
            subprocess.run(
                create_command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # subprocess.run(create_command, check=True, stdout=subprocess.PIPE)
            # subprocess.run(create_command, check=True)
        except Exception as e:
            logging.error(f"FFmpeg command failed: {e}")
            logging.error(f"Command: {' '.join(create_command)}")
            # TODO: log this better!
            pass

        finally:

            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)  # Clean up the temporary file

            # Concatenate the temporary video with the existing in-process video
            if os.path.getsize(temp_video) > 0 and video_mod_time == 0:
                # print("concatenate skip...", temp_video, lcount) # warning
                os.rename(temp_video, in_process_video)
            else:
                ldur2 = get_video_duration(temp_video)
                if os.path.getsize(temp_video) > 0 and ldur2 == 300 / 25:
                    # print("concatenate skip2...", temp_video, lcount) # warning
                    os.rename(temp_video, in_process_video)
                elif round(ldur2, 1) == round(
                    (len(new_files) / 25), 1
                ):  # this is a perfect encode...
                    # print(" detected perfect encode... concatenating...", ldur, ldur2, len(new_files) / 25, video_mod_time, camera_path, os.path.getsize(temp_video), os.path.getsize(in_process_video))
                    concatenate_videos(in_process_video, temp_video, video_path)
                else:
                    # this means a lot of frame drops
                    # print("warning encoding miss!", lcount, video_mod_time, temp_video, os.path.getsize(temp_video) , ldur, ldur2, len(new_files) / 25, os.path.getsize(temp_video), os.path.getsize(in_process_video))
                    # subprocess.run(create_command, check=True)
                    # yeah concatenate anyway
                    concatenate_videos(in_process_video, temp_video, video_path)

    # Add new screenshots to the "in-process" video
    # Assuming screenshots are added at a regular interval, they can be appended in order
    # Here, you would add logic to append new screenshots to the "in-process" video using ffmpeg
    # This part can be complex because ffmpeg doesn't natively append to videos without re-encoding
    # You may want to consider alternative methods of video assembly if frequent appending is required

    return True