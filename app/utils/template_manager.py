# utils/template_manager.py

import os
import re
import shutil
from datetime import datetime

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from werkzeug.utils import secure_filename

from app.config import SCREENSHOT_DIRECTORY, VIDEO_DIRECTORY

from .db import Base, SessionLocal, init_db
from .video_details import get_latest_screenshot_date, get_latest_video_date

from sqlalchemy.orm import validates

class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(32), unique=True, nullable=False)
    frequency = Column(Integer, default=60)
    timeout = Column(Integer, default=10)
    notes = Column(Text, default="")
    motion_filter = Column(String(255), default="")
    last_caption = Column(Text, default="")
    last_caption_time = Column(String(20), default="")
    last_motion_caption = Column(Text, default="")
    last_motion_time = Column(String(20), default="")
    last_screenshot_time = Column(String(20), default="")
    last_video_time = Column(String(20), default="")
    object_filter = Column(String(255), default="")
    object_confidence = Column(Float, default=0.5)
    popup_xpath = Column(String(255), default="")
    dedicated_xpath = Column(String(255), default="")
    callback_url = Column(String(255), default="")
    proxy = Column(String(255), default="")
    url = Column(String(255), default="")
    groups = Column(String(255), default="")
    invert = Column(Boolean, default=False)
    dark = Column(Boolean, default=False)
    headless = Column(Boolean, default=True)
    stealth = Column(Boolean, default=False)
    browser = Column(Boolean, default=False)
    livecaption = Column(Boolean, default=False)
    danger = Column(Boolean, default=False)
    motion = Column(Float, default=0.2)
    rollback_frames = Column(Integer, default=0)

    @validates('name')
    def validate_name(self, key, name):
        if not re.match(r'^[a-zA-Z0-9_-]{1,32}$', name):
            raise ValueError("Name must be 1-32 characters long and contain only letters, numbers, underscores, and hyphens")
        return name

    @validates('frequency')
    def validate_frequency(self, key, frequency):
        if not isinstance(frequency, int) or frequency <= 0 or frequency > 525600:
            raise ValueError("Frequency must be a positive integer not greater than 525600 (1 year)")
        return frequency

    @validates('timeout')
    def validate_timeout(self, key, timeout):
        if not isinstance(timeout, int) or timeout <= 0 or timeout >= self.frequency:
            raise ValueError("Timeout must be a positive integer less than frequency")
        return timeout

    @validates('popup_xpath', 'dedicated_xpath')
    def validate_xpath(self, key, xpath):
        if xpath and not xpath.startswith('//'):
            raise ValueError(f"{key} must start with '//'")
        if len(xpath) > 255:
            raise ValueError(f"{key} must not exceed 255 characters")
        return xpath

    @validates('object_confidence')
    def validate_object_confidence(self, key, confidence):
        if not isinstance(confidence, float) or confidence < 0 or confidence > 1:
            raise ValueError("Object confidence must be a float between 0 and 1")
        return confidence

    @validates('url', 'callback_url')
    def validate_url(self, key, url):
        if url and not url.startswith(('http://', 'https://')):
            raise ValueError(f"{key} must start with http:// or https://")
        if len(url) > 255:
            raise ValueError(f"{key} must not exceed 255 characters")
        return url


class TemplateManager:
    def __init__(self):
        init_db()

    def get_session(self):
        return SessionLocal()

    def get_templates(self):
        session = self.get_session()
        try:
            templates = session.query(Template).all()
            result = {template.name: template.__dict__ for template in templates}
            for key in result:
                del result[key]["_sa_instance_state"]
            if result.get(None):
                del result[None]
            return result
        except Exception as e:
            logging.error(f"Error fetching templates: {str(e)}")
            raise
        finally:
            session.close()

    def save_template(self, name, details):
        if not re.match(r"^[a-zA-Z0-9_-]{1,32}$", name):
            raise ValueError("Invalid template name. Must be 1-32 characters long and contain only letters, numbers, underscores, and hyphens.")

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            if template is None:
                template = Template(name=name)
                session.add(template)
            
            for key, value in details.items():
                if hasattr(template, key):
                    setattr(template, key, value)
                else:
                    logging.warning(f"Ignoring unknown attribute: {key}")

            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logging.error(f"Error saving template: {str(e)}")
            raise
        finally:
            session.close()

    def get_template(self, name):
        if not re.match(r"^[a-zA-Z0-9_-]{1,32}$", name):
            raise ValueError("Invalid template name")

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            if template:
                result = template.__dict__.copy()
                del result["_sa_instance_state"]
                return result
            else:
                return None
        except Exception as e:
            logging.error(f"Error fetching template: {str(e)}")
            raise
        finally:
            session.close()

    def delete_template(self, name):
        if not re.match(r"^[a-zA-Z0-9_-]{1,32}$", name):
            raise ValueError("Invalid template name")

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            if template:
                session.delete(template)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting template: {str(e)}")
            raise
        finally:
            session.close()

    def get_template_by_id(self, template_id):
        if not isinstance(template_id, int) or template_id <= 0:
            raise ValueError("Invalid template ID")

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(id=template_id).first()
            if template:
                result = template.__dict__.copy()
                del result["_sa_instance_state"]
                return result
            else:
                return None
        except Exception as e:
            logging.error(f"Error fetching template by ID: {str(e)}")
            raise
        finally:
            session.close()


def get_templates():
    manager = TemplateManager()
    templates = manager.get_templates()
    for template_name, details in templates.items():
        if template_name is None or template_name == "":
            continue
        camera_path = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(template_name))
        video_path = os.path.join(VIDEO_DIRECTORY, secure_filename(template_name))
        details["last_screenshot_time"] = get_latest_screenshot_date(camera_path)
        details["last_video_time"] = get_latest_video_date(video_path)
    return templates


def get_template(name):
    if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
        return None

    manager = TemplateManager()
    return manager.get_template(name)


def save_template(name: str, template_data) -> bool:
    if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
        return False

    manager = TemplateManager()
    manager.save_template(name, template_data)
    screenshot_full_path = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(name))
    os.makedirs(screenshot_full_path, exist_ok=True)
    video_full_path = os.path.join(VIDEO_DIRECTORY, secure_filename(name))
    os.makedirs(video_full_path, exist_ok=True)

    return True


def delete_template(name: str) -> bool:
    if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
        return False

    manager = TemplateManager()
    success = manager.delete_template(name)
    if success:
        screenshot_full_path = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(name))
        if os.path.exists(screenshot_full_path) and os.path.isdir(screenshot_full_path):
            shutil.rmtree(screenshot_full_path)
        video_full_path = os.path.join(VIDEO_DIRECTORY, secure_filename(name))
        if os.path.exists(video_full_path) and os.path.isdir(video_full_path):
            shutil.rmtree(video_full_path)
    return success


def get_template_by_id(template_id: int):
    manager = TemplateManager()
    return manager.get_template_by_id(template_id)


def get_screenshots_for_template(name: str) -> list:
    if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
        return []
    if not os.path.exists(os.path.join(SCREENSHOT_DIRECTORY, name)):
        return []
    screenshots = [
        f
        for f in os.listdir(os.path.join(SCREENSHOT_DIRECTORY, name))
        if f.startswith(name) and f.endswith(".png") and ".tmp" not in f
    ]
    sorted_screenshots = sorted(
        screenshots,
        key=lambda x: datetime.strptime(x[len(name) + 1 : -4], "%Y%m%d%H%M%S"),
        reverse=True,
    )
    return sorted_screenshots[:10]


def get_videos_for_template(name: str):
    if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
        return []
    if not os.path.exists(os.path.join(VIDEO_DIRECTORY, name)):
        return []
    videos = [
        f
        for f in os.listdir(os.path.join(VIDEO_DIRECTORY, name))
        if (f.startswith(name) or f.startswith('final_')) and f.endswith(".mp4")
    ]
    sorted_videos = sorted(
        videos,
        reverse=True,
    )
    return sorted_videos[:10]
