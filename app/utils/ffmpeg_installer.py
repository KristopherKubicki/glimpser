import os
import platform
import subprocess
import requests
import tarfile
import shutil


def check_ffmpeg_installed():
    """Check if ffmpeg and ffprobe are installed."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_system_architecture():
    """Determine the system architecture."""
    machine = platform.machine().lower()
    if "arm" in machine or "aarch64" in machine:
        return "arm64"
    else:
        return "amd64"


def install_ffmpeg():
    """Download and install ffmpeg and ffprobe."""
    arch = get_system_architecture()
    url = (
        f"https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-{arch}-static.tar.xz"
    )

    try:
        # Download the tarball
        response = requests.get(url)
        response.raise_for_status()

        # Verify the integrity of the downloaded file
        if not response.headers.get('Content-Type') == 'application/x-xz':
            raise ValueError("Downloaded file is not a valid tar.xz archive")

        # Save the tarball
        with open("ffmpeg.tar.xz", "wb") as f:
            f.write(response.content)

        # Extract the tarball
        with tarfile.open("ffmpeg.tar.xz") as tar:
            tar.extractall()

        # Find the extracted directory
        extracted_dir = [d for d in os.listdir() if d.startswith("ffmpeg-")][0]

        # Move ffmpeg and ffprobe to /usr/local/bin
        shutil.move(os.path.join(extracted_dir, "ffmpeg"), "/usr/local/bin/ffmpeg")
        shutil.move(os.path.join(extracted_dir, "ffprobe"), "/usr/local/bin/ffprobe")

        # Set execute permissions
        os.chmod("/usr/local/bin/ffmpeg", 0o755)
        os.chmod("/usr/local/bin/ffprobe", 0o755)

        # Clean up
        os.remove("ffmpeg.tar.xz")
        shutil.rmtree(extracted_dir)

        return True
    except requests.RequestException as e:
        print(f"Error downloading ffmpeg: {e}")
    except tarfile.TarError as e:
        print(f"Error extracting ffmpeg: {e}")
    except (shutil.Error, OSError) as e:
        print(f"Error moving ffmpeg files: {e}")
    except Exception as e:
        print(f"Error installing ffmpeg: {e}")
    return False


def ensure_ffmpeg_installed():
    """Ensure ffmpeg and ffprobe are installed, installing if necessary."""
    if not check_ffmpeg_installed():
        if os.geteuid() == 0:  # Check if running as root
            if install_ffmpeg():
                print("ffmpeg and ffprobe have been successfully installed.")
            else:
                print("Failed to install ffmpeg and ffprobe. Please install manually.")
        else:
            print(
                "ffmpeg and ffprobe are not installed. Please run this script with root privileges to install them."
            )
    else:
        print("ffmpeg and ffprobe are already installed.")
