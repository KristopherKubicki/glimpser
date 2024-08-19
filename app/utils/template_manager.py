# utils/template_manager.py

import os
import re
from datetime import datetime

from sqlalchemy import Boolean, Column, Float, Integer, String, Text

from app.config import SCREENSHOT_DIRECTORY, VIDEO_DIRECTORY

from .db import Base, SessionLocal, init_db
from .video_details import get_latest_screenshot_date, get_latest_video_date


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
            return result
        finally:
            session.close()

    def save_template(self, name, details):
        if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
            return False

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            if template is None:
                template = Template()
                session.add(template)
            if template:
                for key, value in details.items():
                    try:
                        # should read from the model intead
                        if key in [
                            "rollback_frames",
                            "frequency",
                            "timeout",
                        ]:  # HAXKCY!
                            value = int(value)
                        if key in ["object_confidence"]:  # HAXKCY!
                            value = int(value)
                        if key in ["stealth", "headless", "dark", "invert"]:
                            if value == "on":
                                value = True
                            elif value == "off":
                                value = False
                            elif type(value) == bool:
                                pass
                            else:
                                print("MISSSSED", value)
                                continue
                    except Exception:
                        # failing validation... TODO logging
                        continue

                    setattr(template, key, value)
            session.commit()
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
        camera_path = os.path.join(SCREENSHOT_DIRECTORY, template_name)
        video_path = os.path.join(VIDEO_DIRECTORY, template_name)
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
    screenshot_full_path = os.path.join(SCREENSHOT_DIRECTORY, name)
    os.makedirs(screenshot_full_path, exist_ok=True)
    video_full_path = os.path.join(VIDEO_DIRECTORY, name)
    os.makedirs(video_full_path, exist_ok=True)

    return True


def delete_template(name: str) -> bool:
    if not re.findall(r"^[a-zA-Z0-9_\-\.]{1,32}$", name):
        return False

    manager = TemplateManager()
    success = manager.delete_template(name)
    if success:
        screenshot_full_path = os.path.join(SCREENSHOT_DIRECTORY, name)
        if os.path.exists(screenshot_full_path) and os.path.isdir(screenshot_full_path):
            shutil.rmtree(screenshot_full_path)
        video_full_path = os.path.join(VIDEO_DIRECTORY, name)
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
