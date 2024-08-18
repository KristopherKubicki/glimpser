# utils/video_archiver.py

import os
import glob
import subprocess
import datetime
import time 
import tempfile
import random
from PIL import Image
from config import VIDEO_DIRECTORY, MAX_COMPRESSED_VIDEO_AGE, MAX_IN_PROCESS_VIDEO_SIZE, SCREENSHOT_DIRECTORY, VERSION, NAME
from .template_manager import get_templates

def validate_template_name(template_name):

    if template_name is None:
        return False
    if type(template_name) != str:
        return False

    # only allow a-Z0-9_ from 1 to 32 characters
    if re.findall(r'^[a-zA-Z0-9_]{1,32}$', template_name)
        return True

    return False

def touch(fname, times=None):
    with open(fname, 'a'):
        os.utime(fname, times)

def trim_group_name(group_name):
        return group_name.replace(' ', '_').lower()

def compile_to_teaser():
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
    final_videos = {}

    if not os.path.isdir(VIDEO_DIRECTORY):
        return False

    with tempfile.NamedTemporaryFile(mode='w+') as temp_file:
        templates = get_templates()

        for camera, template in templates.items():
            camera_path = os.path.join(VIDEO_DIRECTORY, camera)
            os.makedirs(camera_path, exist_ok=True)

            # Get the most recent "in_process.mp4" video
            video_files = sorted(glob.glob(camera_path + '/*in_process.mp4'), reverse=True)
            if video_files:
                latest_video = video_files[0]
                ldur = get_video_duration(latest_video)
                if ldur < 1:  # not much going on...
                    continue

                # Extract the last 5 seconds of the video
                temp_file.write(f"file '{os.path.abspath(latest_video)}'\n")
                temp_file.write(f"inpoint {max(ldur - 5, 0)}\n")
                temp_file.write(f"outpoint {ldur}\n")

                # Add to group-specific final videos
                groups = template.get('groups', '').split(',')
                for group in groups:
                    trimmed_group_name = group.strip().replace(' ', '_')
                    if trimmed_group_name:
                        if trimmed_group_name not in final_videos:
                            final_videos[trimmed_group_name] = []
                        final_videos[trimmed_group_name].append(os.path.abspath(latest_video))

        # Concatenate the videos without re-encoding for all cameras
        compile_videos(temp_file.name, os.path.join(VIDEO_DIRECTORY, 'all_in_process.mp4'))

        # Concatenate the videos for each group
        for group, videos in final_videos.items():
            with tempfile.NamedTemporaryFile(mode='w+') as group_temp_file: # should be cleaning up automatically...
                for video in videos:
                    group_temp_file.write(f"file '{video}'\n")
                group_temp_file.flush()
                compile_videos(group_temp_file.name, os.path.join(VIDEO_DIRECTORY, f'{group}_in_process.mp4'))


def compile_videos(input_file, output_file):

   if not os.path.exists(input_file):
       return False

    create_command = [
        'ffmpeg',
        '-threads','5',
        '-err_detect', 'ignore_err',
        '-fflags', '+igndts+ignidx+genpts+fastseek+discardcorrupt',
        '-an', '-dn',
        '-f', 'concat',
        '-safe', '0',
        '-i', os.path.abspath(input_file),
        '-c', 'copy',
        '-movflags', '+faststart',
        '-y', os.path.abspath(output_file)
    ]

    try:
        subprocess.run(create_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #print(' cmd:', ' '.join(create_command))
        #subprocess.run(create_command)
        if os.path.exists(output_file) and os.path.getsize(output_file) > 300:
            os.rename(output_file, output_file.replace('.tmp', ''))
            return True
        # otherwise, do something? clean up the file maybe? 
    except Exception as e:
        #print("FFmpeg command failed:", ' '.join(create_command), e)
        # log to an error instead! 
        if os.path.exists(output_file):
            os.unlink(output_file)


def get_video_duration(video_path):

    if not os.path.exists(video_path): # raise? 
        return None


    """Get the duration of a video in seconds."""
    command = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    duration = 0
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = float(result.stdout.strip())
    except Exception as e:
        pass
    return duration

def concatenate_videos(in_process_video, temp_video, video_path):
    """Concatenate the temporary video with the existing in-process video."""
    if os.path.exists(in_process_video) and os.path.exists(temp_video) and os.path.getsize(in_process_video) > 0 and os.path.getsize(temp_video) > 0 and os.path.isdir(video_path):
        in_process_duration = get_video_duration(in_process_video)
        temp_video_duration = get_video_duration(temp_video)
        if in_process_duration > 0 and temp_video_duration > 0:
            concat_video = os.path.join(video_path, 'in_process.concat.mp4')
            concat_command = [
                'ffmpeg',
                '-threads','5',
                '-err_detect', 'ignore_err',
                '-fflags', '+igndts+ignidx+genpts+fastseek+discardcorrupt',
                '-an', '-dn',
                '-c:v', 'h264',
                '-i', os.path.abspath(in_process_video),
                '-i', os.path.abspath(temp_video),
                '-filter_complex', '[0:v:0][1:v:0]concat=n=2:v=1:a=0[outv]',
                '-map', '[outv]',
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                '-y', os.path.abspath(concat_video)  # Overwrite the in-process video
            ]
            try:
                subprocess.run(concat_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                os.rename(concat_video, in_process_video)
                output_video = os.path.join(VIDEO_DIRECTORY, 'latest_camera.mp4')
                if os.path.exists(output_video + '.tmp'):
                    os.unlink(output_video + '.tmp')
                os.symlink(os.path.abspath(in_process_video), os.path.abspath(output_video + '.tmp'))
                os.rename(os.path.abspath(output_video + '.tmp'), os.path.abspath(output_video))

            except Exception as e:
                handle_concat_error(e, temp_video, in_process_video)
        elif os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)
    elif os.path.getsize(temp_video) > 0:
        os.rename(temp_video, in_process_video)


def handle_concat_error(e, temp_video, in_process_video):
    """Handle errors that occur during the concatenation process."""

    if '/in_process.mp4: Invalid data found' in str(e):
        print("Warning: invalid in_process file")
        if os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)
            # TODO: consider truth
    else:
        print("FFmpeg concat command failed:", ' '.join(concat_command), e)
        if os.path.getsize(temp_video) > 0:
            os.rename(temp_video, in_process_video)

def compile_to_video(camera_path, video_path):

    os.makedirs(video_path, exist_ok=True)
    os.makedirs(camera_path, exist_ok=True)

    if not os.path.isdir(video_path):
        return False
    if not os.path.isdir(camera_path):
        return False

    in_process_video = os.path.join(video_path, 'in_process.mp4')

    # Check if there is an "in-process" video and its size
    # TODO: check the creation_time and if it exceeds the alotment, then alos roll over
    if os.path.isfile(in_process_video):
        file_size_exceeded = os.path.getsize(in_process_video) > MAX_IN_PROCESS_VIDEO_SIZE
        file_age_exceeded = (datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(os.path.getctime(in_process_video))).total_seconds() > MAX_COMPRESSED_VIDEO_AGE * 60*60*24*7
 
        # condsider when the length is 2x300 frames as well.  so we always have perfect overlap at 2x

        if file_size_exceeded or file_age_exceeded:
            # Rename the "in-process" video to a "final" video with a timestamp
            final_video_name = f'final_{int(os.path.getmtime(in_process_video))}.mp4'
            # TODO: should we optimize the timing better?
            final_video_path = os.path.join(video_path, final_video_name)
            os.rename(in_process_video, final_video_path)
            #print(f'Video finalized: {final_video_path}')
            # this is going to generate overlapping segments, which is OK for now . 
            

    # Get the modification time of the in-process video
    video_mod_time = os.path.getmtime(in_process_video) if os.path.exists(in_process_video) else 0

    ldur = 0
    if os.path.exists(in_process_video):
        ldur = get_video_duration(in_process_video)
        if ldur < 10 and  time.time() - video_mod_time > 60*60 :  # could be a waste of 300 frames...
            #print("  skipping ", in_process_video, ldur, time.time() - video_mod_time)
            video_mod_time = 0
            # go bigger... 

    if os.path.exists(in_process_video) and ldur >= int(300/25*2): # rotate! 
            # Rename the "in-process" video to a "final" video with a timestamp
            final_video_name = f'final_{int(os.path.getmtime(in_process_video))}.mp4'
            # TODO: should we optimize the timing better?
            final_video_path = os.path.join(video_path, final_video_name)
            os.rename(in_process_video, final_video_path)
            # we should finalize at the END of the encode , right? 
            #print(f'Video finalized: {final_video_path}')  #log instead
            # this is going to generate overlapping segments, which is OK for now . 


    # Filter the list of image files to include only those that are newer than the video
    new_files = [f for f in glob.glob(camera_path + '/*.png') if os.path.getctime(f) > video_mod_time]
    new_files = sorted(new_files)

    if len(new_files) > 0:
        # Create a temporary file with the list of new frames
        lcount = 0
        temp_file_path = None
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
            for file in new_files[-300:]: # keep it short for now 
                if os.path.getsize(os.path.abspath(file)) > 10 and '_2' in file:
                    temp_file.write(f"file '{os.path.abspath(file)}'\n")
                    lcount += 1
            temp_file_path = temp_file.name
        if lcount == 0:
            # nothing to do 
            os.remove(temp_file_path)
            return
        if temp_file_path is None:
            return # should not be possible 

        # Create a temporary video with the new frames
        temp_video = os.path.join(video_path, 'in_process.tmp.mp4')

        create_command = [
            'ffmpeg',
            '-threads','5',
            '-f', 'concat',
            '-r','25', # for some reason the standard for png?
            '-c:v','png',
            '-use_wallclock_as_timestamps', '1',
            '-err_detect','ignore_err',
            '-fflags', '+igndts+ignidx+genpts+fastseek+discardcorrupt',
            '-copyts', '-start_at_zero',
            '-safe', '0',
            '-i', temp_file_path,
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-vf', 'fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',
            '-movflags', '+faststart',
        ]
        create_command.extend(["-metadata", "creation_time=%sZ" % datetime.datetime.utcnow()])
        create_command.extend(["-metadata", "encoded_by=%s" % NAME])
        create_command.extend(["-metadata", "version=%s" % VERSION])
        create_command.extend(['-y', temp_video])  # Overwrite if exists

        try:
            #print("CMD", lcount, ' '.join(create_command))
            subprocess.run(create_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            #subprocess.run(create_command, check=True, stdout=subprocess.PIPE)
            #subprocess.run(create_command, check=True)
        except Exception as e:
            #print("FFmpeg command failed:", e)
            #subprocess.run(create_command, check=True)
            # TODO: log this better! 
            pass

        finally:

            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)  # Clean up the temporary file

            # Concatenate the temporary video with the existing in-process video
            if os.path.getsize(temp_video) > 0 and video_mod_time == 0:
                #print("concatenate skip...", temp_video, lcount) # warning
                os.rename(temp_video, in_process_video)
            else:
                ldur2 = get_video_duration(temp_video)
                if os.path.getsize(temp_video) > 0 and ldur2 == 300/25:
                    #print("concatenate skip2...", temp_video, lcount) # warning
                    os.rename(temp_video, in_process_video)
                elif round(ldur2,1) == round((len(new_files) / 25),1): # this is a perfect encode... 
                    #print(" detected perfect encode... concatenating...", ldur, ldur2, len(new_files) / 25, video_mod_time, camera_path, os.path.getsize(temp_video), os.path.getsize(in_process_video))
                    concatenate_videos(in_process_video, temp_video, video_path)
                else:
                    # this means a lot of frame drops 
                    #print("warning encoding miss!", lcount, video_mod_time, temp_video, os.path.getsize(temp_video) , ldur, ldur2, len(new_files) / 25, os.path.getsize(temp_video), os.path.getsize(in_process_video))
                    #subprocess.run(create_command, check=True)
                    # yeah concatenate anyway
                    concatenate_videos(in_process_video, temp_video, video_path)


    # Add new screenshots to the "in-process" video
    # Assuming screenshots are added at a regular interval, they can be appended in order
    # Here, you would add logic to append new screenshots to the "in-process" video using ffmpeg
    # This part can be complex because ffmpeg doesn't natively append to videos without re-encoding
    # You may want to consider alternative methods of video assembly if frequent appending is required


def archive_screenshots():
    """Background job to compile screenshots into videos."""
    # Ensure VIDEO_DIRECTORY exists
    os.makedirs(VIDEO_DIRECTORY, exist_ok=True)
    os.makedirs(SCREENSHOT_DIRECTORY, exist_ok=True)

    for camera_name in os.listdir(SCREENSHOT_DIRECTORY):
        if not validate_template_name(camera_name):
            continue
        camera_path = os.path.join(SCREENSHOT_DIRECTORY, camera_name)
        if not os.path.isdir(camera_path):  # just a file
            continue
        video_path = os.path.join(VIDEO_DIRECTORY, camera_name)
        os.makedirs(camera_path, exist_ok=True)
        os.makedirs(video_path, exist_ok=True)

        try:
            compile_to_video(camera_path, video_path)
        except Exception as e:
            # TODO: log something bad happening
            pass
        

