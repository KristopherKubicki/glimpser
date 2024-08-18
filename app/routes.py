# app/routes.py

import os, glob, json, time, hashlib, re, io
from flask import render_template, jsonify, send_file, send_from_directory, request, abort, redirect, session, flash, Response, stream_with_context
from datetime import datetime, timedelta

from .utils import screenshots, template_manager, video_archiver, video_details, scheduling
from config import SCREENSHOT_DIRECTORY, VIDEO_DIRECTORY, USER_NAME, SECRET_KEY, USER_PASSWORD_HASH, API_KEY
from werkzeug.security import check_password_hash

from PIL import Image
from functools import wraps
from flask import g, request, redirect, url_for, session
from threading import Lock


def generate_timed_hash():
    expiration_time = int(time.time()) + 15*60
    to_hash = f"{API_KEY}{expiration_time}"
    hash_digest = hashlib.sha256(to_hash.encode()).hexdigest()
    return f"{hash_digest}.{expiration_time}"


def is_hash_valid(timed_hash):
    try:
        hash_digest, expiration_time = timed_hash.split('.')
        to_hash = f"{API_KEY}{expiration_time}"
        valid_hash = hashlib.sha256(to_hash.encode()).hexdigest()
        if int(expiration_time) < int(time.time()):
            return False
        if valid_hash != hash_digest:
            return False
        return True
    except ValueError:
        # Incorrectly formatted hash
        return False


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key in headers, GET parameters, or POST form data
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key') or request.form.get('api_key')
        timed_key = request.args.get('timed_key')
        if timed_key:
            if is_hash_valid(timed_key) is False:
                return jsonify({'error': 'Invalid timed key'}), 401
            return f(*args, **kwargs)
        elif api_key == API_KEY:
            # Bypass session authentication if API key is valid
            return f(*args, **kwargs)
        elif 'logged_in' in session:
            # Proceed with session-based authentication
            return f(*args, **kwargs)
        else:
            # Return an HTTP status error if API key is invalid or missing and not logged in
            if api_key:
                # API key was provided but is invalid
                return jsonify({'error': 'Invalid API key'}), 401
            else:
                # No API key provided, and not logged in
                return redirect(url_for('login', next=request.url))
    return decorated_function

# TODO: 
def generate_video_stream(video_path):
    while True:
        with open(video_path, "rb") as video:
            chunk = video.read(1024 * 1024)  # Read 1 MB at a time
            while chunk:
                yield chunk
                chunk = video.read(1024 * 1024)
        #
        print("sleeping...",)
        time.sleep(30)  # Wait for 5 minutes before streaming the video again


login_attempts = {}
last_shot = None
last_time = None
active_groups = []

def get_active_groups():
        global active_groups
        templates = template_manager.get_templates()
        active_cameras = []
        for id, template in templates.items():
            name = template.get('name')
            if name is None:
               continue

            lgroups = template.get('groups','').strip().split(',')
            for lg in lgroups:
                active_cameras.append(lg.strip())
        active_cameras = sorted(list(set(active_cameras)))
        if '' in active_cameras:
            active_cameras.remove('')
        active_groups = active_cameras.copy()

        return active_cameras


def resize_and_pad(img, size, color=(0, 0, 0)):
    # Calculate the scaling factor to resize the image while maintaining the aspect ratio
    scale = max(size[0] / img.size[0], size[1] / img.size[1])

    # Resize the image using the scaling factor
    new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
    img = img.resize(new_size)

    # Create a new image with the specified size and color
    background = Image.new('RGB', size, color)

    # Paste the resized image onto the center of the background
    x = (size[0] - new_size[0]) // 2
    y = (size[1] - new_size[1]) // 2
    background.paste(img, (x, y))

    return background

lock = Lock()
def generate(group=None, filename='latest_camera.png'):
    # pretty hacky but it works ok
    global last_time, last_shot
    boundary = b'frame'
    while True:
        ltime = time.time() 
        last_path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', SCREENSHOT_DIRECTORY, filename).replace('.png','.jpg')

        frame = None
        if os.path.exists(last_path) and os.path.getsize(last_path) > 0 and os.path.getctime(last_path) > time.time() - 1:
            # just read this image instead... 
            with open(last_path, 'rb') as f:
                frame = f.read()
        else:
          with lock:
            if group is None and last_time and time.time() - last_time < 1 and last_shot and os.path.exists(last_shot):
                # warning - todo, this needs to be completed still
                try:
                    with Image.open(last_shot) as img:
                        img = resize_and_pad(img, (1280, 720))
                        buffer = io.BytesIO()
                        img.save(buffer, format='JPEG')
                        frame = buffer.getvalue()
                except Exception as e:
                    pass # TODO logging
            else:
                # Replace this with your actual template manager code
                templates = template_manager.get_templates()

                #sorted_templates = sorted(templates.items(), key=lambda x: int(x[1].get('last_video_time', 0) or 0), reverse=True)
                sorted_templates = templates.items() # there is a problem with the sort.. 

                most_recent_time = 0
                most_recent_file = None
                # there is some kind of bug in here where we will sometimes pick an image before we should (like if its not captioned yet)
                for template_id, template_details in sorted_templates:
                    template_name = template_details.get('name')
                    if template_name is None:
                        continue

                    template_groups = []
                    if group and 'groups' in template_details:
                        template_groups = [g.strip() for g in template_details['groups'].split(',')]
                        if group not in template_groups:
                            continue
                    elif group:
                        continue


                    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', SCREENSHOT_DIRECTORY, template_name)
                    # no need to loop through the directory if we find the symlink file
                    lfiles = []
                    if os.path.exists(os.path.join(path, filename)):
                        lfiles = [os.path.join(path, filename)]

                    last_file = lfiles[-1] if lfiles else None
                    if last_file and os.path.exists(last_file) and (os.path.getmtime(last_file) > most_recent_time or most_recent_file is None):
                        most_recent_file = last_file
                        most_recent_time = os.path.getmtime(last_file)

                frame = None
                if most_recent_file:
                    last_time = time.time()
                    last_shot = most_recent_file

                    try:
                        with Image.open(most_recent_file) as img:
                            img = resize_and_pad(img, (1280, 720))
                            buffer = io.BytesIO()
                            img.save(buffer, format='JPEG')
                            frame = buffer.getvalue()
                            # file sizes the same size?  maybe just touch the file instead? 

                            # write this to a file! cache it.  read that cache if possible 
                            with open(last_path,'wb') as f:
                                f.write(frame)
                            # only do this if the files are different.  otherwise, just freshen up maybe? 
                            os.rename(last_path,last_path.replace('.tmp',''))
                    except Exception as e:
                        #print(" warning: png error", e)
                        pass

        if frame:
            yield b'--' + boundary + b'\r\n'
            yield b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n'
        if time.time() - ltime > 1:
            continue
        time.sleep(1 - (time.time() - ltime))

def init_routes(app):
    global login_attempts
    #get_active_groups()

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        ip_address = request.remote_addr
        now = datetime.now()

        # Check if the IP address is locked out
        if ip_address in login_attempts and login_attempts[ip_address]['locked_until'] > now:
            return 'Too many failed attempts. Please try again later.', 429

        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            if username == USER_NAME and check_password_hash(USER_PASSWORD_HASH, password):
                session['logged_in'] = True
                login_attempts.pop(ip_address, None)  # Reset attempts on successful login
                return redirect(url_for('index'))
            else:
                # Record the failed attempt
                if ip_address not in login_attempts:
                    login_attempts[ip_address] = {'attempts': 1, 'locked_until': now}
                else:
                    login_attempts[ip_address]['attempts'] += 1
   
                # Lockout after 5 failed attempts
                if login_attempts[ip_address]['attempts'] >= 5:
                    login_attempts[ip_address]['locked_until'] = now + timedelta(hours=24)

                # Rate limit after 2 attempts per minute
                if login_attempts[ip_address]['attempts'] % 2 == 0:
                    login_attempts[ip_address]['locked_until'] = now + timedelta(minutes=1)

                flash('Invalid username or password')
        return render_template('login.html')

    @app.route('/logout')
    #@login_required
    def logout():
        session.pop('logged_in', None)
        return redirect(url_for('login'))

    @app.route('/')
    @login_required
    def index():
        # TODO: maybe include the template details
        return render_template('index.html')


    def get_active_templates():
        templates = template_manager.get_templates()
        active_cameras = []
        for id, template in templates.items():
            name = template.get('name')
            last_screenshot_time = template.get('last_screenshot_time')
            if last_screenshot_time:
                last_update = datetime.strptime(last_screenshot_time, "%Y-%m-%d %H:%M:%S")
                if last_update > datetime.utcnow() - timedelta(days=1):
                    active_cameras.append(template)
        return active_cameras

    @app.route('/submit_image/<template_name>', methods=['POST'])
    @login_required
    def submit_image(template_name):
        """
        Endpoint to receive and process an image submitted by a remote service or camera.
        """
        # Check if the template exists
        print("WARNING BRPKEN!")
        ltemplate = template_manager.get_template(template_name)
        if ltemplate is None:
            return jsonify({'status': 'error', 'message': 'Template not found'}), 404
        template_name = ltemplate.get('name')

        # Check if the request has the file part
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file part in the request'}), 400

        file = request.files['file']

        # If the user does not select a file, the browser submits an empty file without a filename
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file'}), 400

        if file and allowed_file(file.filename):
            # Generate a unique timestamped filename
            timestamp = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
            filename = f"{template_name}_{timestamp}.png.tmp"
            output_path = os.path.join(SCREENSHOT_DIRECTORY, template_name, filename)

            # Save the file to a temporary location
            file.save(output_path)

            # Add a timestamp to the image and remove the ".tmp" extension
            add_timestamp(output_path, name=template_name)
            final_path = output_path.rstrip('.tmp')
            os.rename(output_path, final_path)

            # Update the template's last screenshot time
            template_manager.update_last_screenshot_time(template_name)

            return jsonify({'status': 'success', 'message': 'Image submitted successfully'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Invalid file format'}), 400
    
    @app.route('/stream.png')
    @login_required
    def stream_png():

        if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', SCREENSHOT_DIRECTORY,'latest_camera.png')):
            return send_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', SCREENSHOT_DIRECTORY,'latest_camera.png'))

        global last_time, last_shot
        # implement some simple caching so the server doesn't get crushed 
        if last_time and time.time() - last_time < 1 and last_shot and os.path.exists(last_shot):
            return send_file(last_shot)
        
        templates = template_manager.get_templates()
        sorted_templates = sorted(templates.items(), key=lambda x: (x[1].get('last_video_time', 0) or 0), reverse=True)

        most_recent_time = 0
        most_recent_file = None
        last_file = None
        for template in sorted_templates:
            name = template.get('name')
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', SCREENSHOT_DIRECTORY, name)
            lfiles = [f for f in glob.glob(path + '/*.png') if os.path.isfile(f)]
            lfiles.sort(key=os.path.getmtime)
            last_file = lfiles[-1]
            if os.path.exists(last_file) and os.path.getmtime(last_file) > most_recent_time:
                most_recent_file = last_file
                most_recent_time = os.path.getmtime(last_file)
        if most_recent_file is None:
            abort(404)

        last_time = time.time()
        last_shot = most_recent_file

        if os.path.exists(most_recent_file):
            return send_file(most_recent_file)
        return send_file(last_file) # better than nothing

    @app.route('/test.rtsp', methods=['OPTIONS', 'DESCRIBE', 'SETUP', 'PLAY', 'TEARDOWN'])
    def handle_rtsp(camera_hash):
        session_id = request.headers.get('Session', generate_session_id())
        if request.method == 'OPTIONS':
            return Response('Public: OPTIONS, DESCRIBE, SETUP, TEARDOWN, PLAY', headers={'CSeq': request.headers.get('CSeq', '0')})

        elif request.method == 'DESCRIBE':
            # Return a mock SDP description
            sdp = 'v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=No Name\r\nt=0 0\r\na=tool:libavformat 58.20.100\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n'
            return Response(sdp, mimetype='application/sdp', headers={'CSeq': request.headers.get('CSeq', '0')})

        elif request.method == 'SETUP':
            return Response(headers={'CSeq': request.headers.get('CSeq', '0'), 'Session': session_id, 'Transport': request.headers.get('Transport', '')})

        elif request.method == 'PLAY':
            # Start streaming video (not implemented)
            return Response(headers={'CSeq': request.headers.get('CSeq', '0'), 'Session': session_id})

        elif request.method == 'TEARDOWN':
            # Stop streaming video (not implemented)
            return Response(headers={'CSeq': request.headers.get('CSeq', '0'), 'Session': session_id})

        return 'Method Not Allowed', 405

 
    @app.route('/stream.mjpg', methods=['GET'])
    def stream_mjpg():
        group = request.args.get('group')
        return Response(generate(group=group, filename='latest_camera.png'), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/motion.mjpg', methods=['GET'])
    def motion_mjpg():
        group = request.args.get('group')
        return Response(generate(group=group, filename='last_motion.png'), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/caption.mjpg', methods=['GET'])
    def caption_mjpg():
        group = request.args.get('group')
        print("last caption")
        return Response(generate(group=group, filename='last_caption.png'), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/motion_caption.mjpg', methods=['GET'])
    def motion_caption_mjpg():
        group = request.args.get('group')
        print("last motion caption")
        return Response(generate(group=group, filename='last_motion_caption.png'), mimetype='multipart/x-mixed-replace; boundary=frame')


    @app.route('/stream.mp4')
    @login_required
    def stream_mp4():
        # Default group
        lgroup = 'all'

        # Get the group from the request arguments and validate
        group = request.args.get('group')
        if group and re.match(r'^[a-zA-Z0-9_]+$', group):
            lgroup = group
        else:
            # If the group is provided but invalid, return a 400 Bad Request
            if group:
                abort(400, "Invalid group name. Group name must be alphanumeric.")

        video_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', VIDEO_DIRECTORY, f'{lgroup}_in_process.mp4')
        if not os.path.exists(video_path):
            abort(404)
        return send_file(video_path)
        # TODO: implement slowstreaming and continuous streaming
        #return Response(stream_with_context(generate_video_stream(video_path)), mimetype='video/mp4')

    @app.route('/stream.m3u8')
    @login_required
    def playlist_m3u8():
        path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', VIDEO_DIRECTORY)
    
        # Check if the video directory exists
        if not os.path.exists(path):
            abort(404)

        # Fetch all camera names or identifiers you have

        # Generate playlist content
        media_sequence = str(datetime.utcnow())[:18].replace(' ','').replace('-','')
        playlist_content = '#EXTM3U\n'
        #playlist_content += '#EXT-X-VERSION:3\n'
        #playlist_content += '#EXT-X-TARGETDURATION:10\n'  # Assuming each segment is up to 10 seconds
        #playlist_content += f'#EXT-X-MEDIA-SEQUENCE:{media_sequence}\n'  # Increment this with each update

        templates = template_manager.get_templates()
        # Sort templates by 'last_video_time' descending
        sorted_templates = sorted(templates.items(), key=lambda x: (x[1].get('last_video_time', 0) or 0), reverse=True)

        for camera_id, template in templates.items():
            camera_name = template.get('name')
            # Assuming the MP4 file is the segment
            lkey = generate_timed_hash()
            video_path = f'{request.url_root}last_video/{camera_name}?timed_key={lkey}'
            playlist_content += f'#EXTINF:-1,{camera_name}\n{video_path}\n'

        return Response(playlist_content, mimetype='application/x-mpegURL')

    @app.route('/stream')
    @login_required
    def stream():
        # Get a list of active cameras (with updates within the last 1 day)
        return render_template('stream.html')


    @app.route('/groups')
    @login_required
    def get_groups():
        # Assuming you have a function that returns a list of unique groups
        groups = get_active_groups()
        return jsonify(groups)

    @app.route('/captions')
    @login_required
    def captions():

        # Specify the directory containing the .jl files
        directory = 'data/summaries/'

        # Get all files in the directory
        files = os.listdir(directory)

        # Filter out only .jl files and sort them by last modified time in descending order
        jl_files = sorted([file for file in files if file.endswith('.jl')], key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)

        # Load entries from the most recent 5 .jl files
        entries = []
        for file in jl_files[:5]:
             file_path = os.path.join(directory, file)
             with open(file_path, 'r') as f:
                 try:
                     data = json.load(f)
                     entries.append(data)
                 except Exception as e:
                     pass

        # Get a list of active cameras (with updates within the last 1 day)
        return render_template('captions.html', template_details=template_manager.get_templates(), lcaptions=entries)


    @app.route('/live')
    @login_required
    def live():
        # Get a list of active cameras (with updates within the last 1 day)
        return render_template('live.html', template_details=template_manager.get_templates())

    # TODO: extend this for groups
    @app.route('/last_teaser')
    @login_required
    def serve_teaser():
        """
        Serve the group teaser video
        """
        # Placeholder logic to serve the screenshot
        path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', VIDEO_DIRECTORY)
        if not os.path.exists(path):
            abort(404)

        if os.path.exists(path + '/all_in_process.mp4'):
            return send_file(path + '/all_in_process.mp4')

        abort(404)


    @app.route('/last_video/<template_name>')
    @login_required
    def serve_video(template_name):
        """
        Serve a specific screenshot by template name.
        """
        if not re.findall(r'^[a-zA-Z0-9_]{1,32}$',template_name):
            abort(404)

        # Placeholder logic to serve the screenshot
        path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', VIDEO_DIRECTORY, template_name)
        if not os.path.exists(path):
            abort(404)

        if os.path.exists(path + '/in_process.mp4'):
            return send_file(path + '/in_process.mp4')

        abort(404)


    @app.route('/last_screenshot/<template_name>')
    @login_required
    def serve_screenshot(template_name):
        """
        Serve a specific screenshot by template name.
        """
        if not re.findall(r'^[a-zA-Z0-9_]{1,32}$',template_name):
            abort(404)

        # Placeholder logic to serve the screenshot
        path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', SCREENSHOT_DIRECTORY, template_name)
        if not os.path.exists(path):
            abort(404)

        lfiles = [f for f in glob.glob(path + '/*.png') if os.path.isfile(f)]
        lfiles.sort(key=os.path.getmtime)
        if len(lfiles) > 0:
            return send_file(lfiles[-1])

        abort(404)
       
    @app.route('/compile_teaser', methods=['GET'])
    @login_required
    def take_compile():
        video_archiver.compile_to_teaser()
        return jsonify({'status': 'success', 'message': f'Compilation taken'})


    @app.route('/upload_screenshot/<template_name>', methods=['POST'])
    @login_required
    def upload_screenshot(template_name):
        """
        Endpoint to upload a screenshot manually.
        """
        if not re.findall(r'^[a-zA-Z0-9_]{1,32}$',template_name):
            abort(404)

        if 'image_file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No image file provided'}), 400

        image_file = request.files['image_file']
        if image_file.filename == '':
            return jsonify({'status': 'error', 'message': 'No image file provided'}), 400

        print("TODO: rewrite")
        templates = template_manager.get_templates()
        if templates.get(template_name) is None:
            abort(404)

        # TODO: add more handling around this
        # Save the uploaded file to a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            image_file.save(temp_file.name)
            # Call the update_camera function with the temporary file path
            scheduling.update_camera(template_name, templates.get(template_name), image_file=temp_file.name)
            # potentially trigger motion too... 
        
        # Clean up the temporary file
        os.unlink(temp_file.name)

        return jsonify({'status': 'success', 'message': f'Screenshot for {template_name} uploaded'})


    @app.route('/take_screenshot/<template_name>', methods=['POST','GET'])
    @login_required
    def take_screenshot(template_name):
        """
        Endpoint to trigger screenshot capture manually.
        """
        if not re.findall(r'^[a-zA-Z0-9_]{1,32}$',template_name):
            abort(404)

        templates = template_manager.get_templates()
        # handle if this doesn't exist
        if templates.get(template_name) is None:
            abort(404)

        # TODO: consider adding motion control
        scheduling.update_camera(template_name, templates.get(template_name))
        return jsonify({'status': 'success', 'message': f'Screenshot for {template_name} taken'})

    @app.route('/update_video/<template_name>', methods=['POST'])
    @login_required
    def update_video(template_name):
        """
        Endpoint to trigger screenshot capture manually.
        """
        if not re.findall(r'^[a-zA-Z0-9_]{1,32}$',template_name):
            abort(404)

        templates = template_manager.get_templates()
        # handle if this doesn't exist
        if templates.get(template_name) is None:
            abort(404)
        camera_path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', SCREENSHOT_DIRECTORY, template_name)
        video_path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', VIDEO_DIRECTORY, template_name)
        video_archiver.compile_to_video(camera_path, video_path)
        return jsonify({'status': 'success', 'message': f'Screenshot for {template_name} taken'})

    @app.route('/templates', methods=['GET', 'POST', 'DELETE'])
    @login_required
    def manage_templates():
        if request.method == 'POST':
            data = request.json
            if template_manager.save_template(data['name'], data):
                return jsonify({'status': 'success', 'message': 'Template saved'})

        elif request.method == 'GET':
            group = request.args.get('group')
            templates = template_manager.get_templates()

            if group and group != 'all':
                # Assuming each template has a 'groups' field which is a comma-separated list of groups
                filtered_templates = {name: template for name, template in templates.items() if group in template.get('groups', '').split(',')}
                return jsonify(filtered_templates)
            else:
                return jsonify(templates)

        elif request.method == 'DELETE':
            data = request.json
            if template_manager.delete_template(data['name']):
                return jsonify({'status': 'success', 'message': 'Template deleted'})
            else:
                return jsonify({'status': 'failure', 'message': 'Template not found'}), 404


    @app.route('/templates/<template_name>')
    @login_required
    def template_details(template_name):
        templates = template_manager.get_templates()
        # handle if this doesn't exist
        if templates.get(template_name) is None:
            abort(404)

        template_details = templates.get(template_name)
        lscreenshots = template_manager.get_screenshots_for_template(template_name)
        if lscreenshots is None:
            abort(404)  # Template not found
        videos = template_manager.get_videos_for_template(template_name)
        return render_template('template_details.html', template_name=template_name, template_details=template_details, lscreenshots=screenshots, videos=videos)


    @app.route('/screenshots/<name>/<filename>')
    @login_required
    def uploaded_file(name, filename):
        # TODO: make this more robust
        path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', SCREENSHOT_DIRECTORY, name)
        if not os.path.exists(path):
            abort(404)

        return send_from_directory(path, filename)

    @app.route('/videos/<name>/<filename>')
    @login_required
    def view_video(name, filename):
        # TODO: make this more robust
        path = os.path.join(os.path.dirname(os.path.join(__file__)),'..', VIDEO_DIRECTORY, name)
        if not os.path.exists(path):
            abort(404)

        return send_from_directory(path, filename)


    @app.route('/update_template/<template_name>', methods=['POST'])
    @login_required
    def update_template(template_name):
        # TODO: refactor the template validation name

        if request.method == 'POST' and re.findall(r'^[a-zA-Z0-9_]{1,32}$',template_name): # make sure it matches our quality thresholds
            # Extract form data

            updated_data = {
                'url': request.form.get('url'),
                'frequency': request.form.get('frequency'),
                'timeout': request.form.get('timeout'),
                'notes': request.form.get('notes'),
                'popup_xpath': request.form.get('popup_xpath'),
                'dedicated_xpath': request.form.get('dedicated_xpath'),
                'callback_url': request.form.get('callback_url'),
                'proxy': request.form.get('proxy'),
                'rollback_frames': request.form.get('rollback_frames'),
                'groups': request.form.get('groups'),
                'object_filter': request.form.get('object_filter'),
                'object_confidence': request.form.get('object_confidence',0.5),
                'motion': request.form.get('motion',0.2),
                'invert': request.form.get('invert', 'false').lower() in ['true', '1', 't', 'y', 'yes','on'],
                'dark': request.form.get('dark', 'false').lower() in ['true', '1', 't', 'y', 'yes','on'],
                'headless': request.form.get('headless', 'false').lower() in ['true', '1', 't', 'y', 'yes','on'],
                'stealth': request.form.get('stealth', 'false').lower() in ['true', '1', 't', 'y', 'yes','on'],
                'browser': request.form.get('browser', 'false').lower() in ['true', '1', 't', 'y', 'yes','on'],
                'livecaption': request.form.get('livecaption', 'false').lower() in ['true', '1', 't', 'y', 'yes','on'],
                'danger': request.form.get('danger', 'false').lower() in ['true', '1', 't', 'y', 'yes','on']
            }

            lremoves = []
            for lkey in updated_data:
                if updated_data.get(lkey) is None:
                    lremoves.append(lkey)
            for lkey in lremoves:
                del updated_data[lkey]

            # TODO: validate

            if updated_data.get('rollback_frames') == '':
                updated_data['rollback_frames'] = 0
            if updated_data.get('timeout') == '':
                updated_data['timeout'] = 30
            if updated_data.get('frequency') == '':
                updated_data['frequency'] = 30

            # Update the template in your storage (e.g., JSON file, database)
            # This assumes you have a function to update templates
            update_success = template_manager.save_template(template_name, updated_data)

            # TODO: stop the old job.  reschedule the camera
            updated_template = template_manager.get_template(template_name)
            try:
                seconds = int(updated_data.get('frequency',30*60))
                scheduling.scheduler.add_job(func=scheduling.update_camera, trigger='interval', seconds=seconds, args=[template_name, updated_data], id=template_name, replace_existing=True)
            except Exception as e:
                print("job schedule error:", e)
                #logging.error(f"Error scheduling job for {name}: {e}")


            if request.is_json:
                return jsonify({'message': 'Template updated successfully!'})

            return redirect('/templates/' + template_name)


