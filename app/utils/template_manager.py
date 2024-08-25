# app/utils/template_manager.py

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
    name = Column(String, unique=True, nullable=False)
    frequency = Column(Integer, default=60)
    timeout = Column(Integer, default=10)
    notes = Column(Text, default="")
    motion_filter = Column(String, default="")
    last_caption = Column(Text, default="")
    last_caption_time = Column(String, default="")
    last_motion_caption = Column(Text, default="")
    last_motion_time = Column(Text, default="")
    last_screenshot_time = Column(Text, default="")
    last_video_time = Column(Text, default="")
    object_filter = Column(String, default="")
    object_confidence = Column(Float, default=0.5)
    popup_xpath = Column(String, default="")
    dedicated_xpath = Column(String, default="")
    callback_url = Column(String, default="")
    proxy = Column(String, default="")
    url = Column(String, default="")
    groups = Column(String, default="")
    invert = Column(Boolean, default=False)
    dark = Column(Boolean, default=False)
    headless = Column(Boolean, default=True)
    stealth = Column(Boolean, default=False)
    browser = Column(Boolean, default=False)
    livecaption = Column(Boolean, default=False)
    danger = Column(Boolean, default=False)
    motion = Column(Float, default=0.2)
    rollback_frames = Column(Integer, default=0)

    @validates('frequency')
    def validate_frequency(self, key, frequency):
        if frequency > 525600:
            raise ValueError("Frequency cannot be greater than 525600 (1 year)")
        return frequency

    @validates('timeout')
    def validate_timeout(self, key, timeout):
        if timeout >= self.frequency:
            raise ValueError("Timeout must be less than frequency")
        return timeout

    @validates('popup_xpath', 'dedicated_xpath')
    def validate_xpath(self, key, xpath):
        if xpath and not xpath.startswith('//'):
            raise ValueError(f"{key} must start with '//'")
        return xpath

    @validates('object_confidence')
    def validate_object_confidence(self, key, confidence):
        if self.object_filter and (confidence < 0 or confidence > 1):
            raise ValueError("Object confidence must be between 0 and 1")
        return confidence


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
        finally:
            session.close()

    def save_template(self, name, details):

        # TODO: replace this with validate_template_name instead 
        if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
            return False

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            if template is None:
                template = Template()
                session.add(template)
            ldelta = False
            if template:
                for key, value in details.items():
                    try:
                        if key == "rollback_frames":
                            value = int(value)
                        elif key in ["frequency", "timeout"]:
                            if value == "":
                                value = 30

                            value = int(value)
                            if key == "frequency" and value > 525600:
                                raise ValueError("Frequency cannot be greater than 525600 (1 year)")
                            if key == "timeout" and value >= int(details.get("frequency", template.frequency) * 60):
                                value = details.get("frequency", template.frequency) * 60
                                #raise ValueError("Timeout must be less than frequency")
                        elif key == "object_confidence":
                            if value == "":
                                value = 0.5
                            value = float(value)
                            if details.get("object_filter", template.object_filter) and (value < 0 or value > 1):
                                raise ValueError("Object confidence must be between 0 and 1")
                        elif key in ["popup_xpath", "dedicated_xpath"]:
                            if value and not value.startswith('//'):
                                raise ValueError(f"{key} must start with '//'")
                        elif key in ["stealth", "headless", "dark", "invert"]:
                            if value == "on":
                                value = True
                            elif value == "off":
                                value = False
                            elif type(value) == bool:
                                pass
                            else:
                                print("MISSSSED", value)
                                continue
                    except ValueError as e:
                        # Log the validation error and return False
                        print(f"Validation error: {str(e)}", name, key, value)
                        return False

                    # check to make sure a change actually occurred
                    if getattr(template, key) != value:
                        setattr(template, key, value)
                        ldelta = True
            if ldelta is True:
                session.commit()
            return True
        except Exception as e:
            print(f"Error saving template: {str(e)}")
            return False
        finally:
            session.close()

    def get_template(self, name):
        if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
            return False

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            result = template.__dict__ if template else {}
            if "_sa_instance_state" in result:
                del result["_sa_instance_state"]
            return result
        finally:
            session.close()

    def delete_template(self, name):
        if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
            return False

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            if template:
                session.delete(template)
                session.commit()
                return True
            return False
        finally:
            session.close()

    def get_template_by_id(self, template_id):
        # TODO: validate id
        session = self.get_session()
        try:
            template = session.query(Template).filter_by(id=template_id).first()
            result = template.__dict__ if template else {}
            if "_sa_instance_state" in result:
                del result["_sa_instance_state"]
            return result
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
