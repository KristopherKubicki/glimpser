# app/utils/template_manager.py

import os
import shutil
import random
import logging
import json
from datetime import datetime

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from werkzeug.utils import secure_filename
from .validators import validate_template_name

from app.config import SCREENSHOT_DIRECTORY, VIDEO_DIRECTORY

import app.utils.db as db
from .video_details import get_latest_screenshot_date, get_latest_video_date

from sqlalchemy.orm import validates

# Keep aliases for backward compatibility and testing mocks
SessionLocal = db.SessionLocal
init_db = db.init_db
ensure_column = db.ensure_column
Base = db.Base

LLM_USAGE_PATH = "data/llm_usage.json"
LLM_COST_PER_TOKEN = 0.005 / 1000  # OpenAI pricing example


def is_snapshot_url(url: str) -> bool:
    """Return ``True`` when ``url`` points to a still image endpoint."""

    if not url:
        return False
    url = url.lower()
    return (
        url.endswith((".jpg", ".jpeg", ".png")) or "snapshot" in url or "picture" in url
    )


class Template(db.Base):
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
    offline_since = Column(Text, default="")
    capture_failed = Column(Boolean, default=False)
    object_filter = Column(String, default="")
    object_confidence = Column(Float, default=0.5)
    popup_xpath = Column(String, default="")
    dedicated_xpath = Column(String, default="")
    callback_url = Column(String, default="")
    proxy = Column(String, default="")
    auth_username = Column(String, default="")
    auth_password = Column(String, default="")
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
    last_ret = None

    @validates("frequency")
    def validate_frequency(self, key, frequency):
        if frequency > 525600:
            raise ValueError("Frequency cannot be greater than 525600 (1 year)")
        return frequency

    @validates("timeout")
    def validate_timeout(self, key, timeout):
        if timeout < 1:
            logging.warning("negative timeout")
            timeout = 10
        if timeout >= float(self.frequency) * 60:
            timeout = float(self.frequency) * 60
            raise ValueError(f"timeout calculation error {timeout} {self.frequency}")
        return timeout

    @validates("popup_xpath", "dedicated_xpath")
    def validate_xpath(self, key, xpath):
        if xpath and not xpath.startswith("//"):
            raise ValueError(f"{key} must start with '//'")
        return xpath

    @validates("object_confidence")
    def validate_object_confidence(self, key, confidence):
        if self.object_filter and (confidence < 0 or confidence > 1):
            raise ValueError("Object confidence must be between 0 and 1")
        return confidence


class TemplateManager:
    """Manage :class:`Template` records stored in the database.

    The manager initializes the SQLite database on construction and
    provides helper methods for retrieving a database session. Public
    methods perform validation and commit changes when updating or
    deleting templates.
    """

    def __init__(self):
        init_db()
        # Ensure the templates table exists even when Base has been reloaded
        Template.__table__.create(db.engine, checkfirst=True)
        # Automatically add newer columns when upgrading from older versions
        ensure_column("templates", "capture_failed", "BOOLEAN", "0")
        ensure_column("templates", "auth_username", "VARCHAR(255)", "''")
        ensure_column("templates", "auth_password", "VARCHAR(255)", "''")

    def get_session(self):
        """Return a new SQLAlchemy session bound to the app database."""

        return SessionLocal()

    def get_templates(self):
        """Return all templates from the database as a dictionary.

        Returns
        -------
        dict
            Mapping of template name to its stored attributes with
            SQLAlchemy internal state removed.
        """

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

    def get_templates_by_last_caption_time(self):
        """Return templates ordered by ``last_caption_time`` descending.

        Returns
        -------
        list
            Tuples of template name and attribute dicts sorted newest first.
        """

        session = self.get_session()
        try:
            templates = (
                session.query(Template)
                .order_by(Template.last_caption_time.desc())
                .all()
            )
            result = []
            for template in templates:
                if template.name is None or template.name == "":
                    continue
                data = template.__dict__.copy()
                data.pop("_sa_instance_state", None)
                result.append((template.name, data))
            return result
        finally:
            session.close()

    def save_template(self, name, details):
        """Create or update a template in the database.

        Parameters
        ----------
        name : str
            Template name to validate and store.
        details : dict
            Dictionary of template attributes.

        Returns
        -------
        bool
            ``True`` when the template was saved successfully,
            ``False`` if validation failed or an error occurred.
        """

        name = validate_template_name(name)
        if name is None:
            return False

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            if template is None:
                template = Template()
                session.add(template)
                ldelta = True
            else:
                ldelta = False

            # Determine whether this template operates in browser/stealth mode.
            browser_like = bool(details.get("browser", template.browser)) or bool(
                details.get("stealth", template.stealth)
            )

            # Default frequency/timeout to higher values when using a real
            # browser. Pages take longer to load and should be scraped more
            # politely. This mirrors validation defaults but also covers direct
            # TemplateManager usage without prior normalization. See
            # ``docs/configuration_guide.md`` for rationale.
            default_frequency = 60 if browser_like else 30
            default_timeout = 30 if browser_like else 10
            if "frequency" not in details or details.get("frequency") == "":
                details["frequency"] = default_frequency
            if "timeout" not in details or details.get("timeout") == "":
                details["timeout"] = default_timeout
            if template:
                for key, value in details.items():
                    if not hasattr(template, key):
                        # Ignore keys that are not valid attributes on
                        # the Template model. This prevents errors when
                        # extraneous fields like ``snapshot_only`` are
                        # submitted from the UI.
                        continue
                    try:
                        if key == "rollback_frames":
                            value = int(value)
                        elif key in ["frequency", "timeout"]:
                            if value == "":
                                value = (
                                    default_frequency
                                    if key == "frequency"
                                    else default_timeout
                                )

                            value = int(value)
                            if key == "frequency" and value > 525600:
                                value = 525600
                            if (
                                key == "frequency" and value < 0.01
                            ):  # that's less than 1 fps...
                                value = 0.01

                            if (
                                key == "timeout"
                                and value
                                >= float(details.get("frequency", template.frequency))
                                * 60
                            ):
                                value = (
                                    int(details.get("frequency", template.frequency))
                                    * 60
                                )  # adjust the timeout down
                            if key == "timeout" and value < 1:
                                value = 1

                        elif key == "object_confidence":
                            if value == "":
                                value = 0.5
                            value = float(value)
                            if details.get(
                                "object_filter", template.object_filter
                            ) and (value < 0 or value > 1):
                                raise ValueError(
                                    "Object confidence must be between 0 and 1"
                                )
                        elif key in ["popup_xpath", "dedicated_xpath"]:
                            if value and not value.startswith("//"):
                                raise ValueError(f"{key} must start with '//'")
                        elif key in ["stealth", "headless", "dark", "invert"]:
                            if value == "on":
                                value = True
                            elif value == "off":
                                value = False
                            elif isinstance(value, bool):
                                pass
                            else:
                                logging.debug("MISSSSED %s", value)
                                continue
                    except ValueError as e:
                        # Log the validation error and return False
                        logging.warning("Validation error: %s %s %s", str(e), name, key)
                        return False

                    # check to make sure a change actually occurred
                    if getattr(template, key) != value:
                        setattr(template, key, value)
                        ldelta = True
            if ldelta is True:
                session.commit()
                # Recreate the scheduler job so the new settings take effect
                _update_scheduler_job(name, template.frequency)
            return True
        except Exception as e:
            logging.error("Error saving template: %s", str(e))
            return False
        finally:
            session.close()

    def get_template(self, name):
        """Return a single template by name.

        Parameters
        ----------
        name : str
            Template name to fetch from the database.

        Returns
        -------
        dict
            Stored template attributes or an empty ``dict`` when the
            name fails validation or is not present.
        """
        name = validate_template_name(name)
        if name is None:
            return False

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=name).first()
            result = template.__dict__ if template else {}
            if "_sa_instance_state" in result:
                del result["_sa_instance_state"]
            if result:
                result["snapshot_only"] = is_snapshot_url(result.get("url", ""))
            return result
        finally:
            session.close()

    def delete_template(self, name):
        """Delete a template from the database.

        Parameters
        ----------
        name : str
            Template name to remove.

        Returns
        -------
        bool
            ``True`` if the template existed and was deleted,
            otherwise ``False``.
        """
        name = validate_template_name(name)
        if name is None:
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
        """Return template details for ``template_id`` if valid.

        Parameters
        ----------
        template_id : int
            Primary key of the template record.

        Returns
        -------
        dict
            Template attributes or an empty ``dict`` if the ID is
            invalid or not found.
        """

        # Validate ``template_id`` before opening a session
        if not isinstance(template_id, int) or template_id <= 0:
            return {}

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
    """Return all templates enriched with filesystem metadata.

    Returns
    -------
    dict
        Template attributes keyed by name with additional
        ``last_screenshot_time`` and ``last_video_time`` fields
        populated from the screenshot and video directories.
    """

    manager = TemplateManager()
    templates = manager.get_templates()
    for template_name, details in templates.items():
        if template_name is None or template_name == "":
            continue
        valid_name = validate_template_name(template_name)
        if valid_name is None:
            continue
        camera_path = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(valid_name))
        video_path = os.path.join(VIDEO_DIRECTORY, secure_filename(valid_name))
        details["last_screenshot_time"] = get_latest_screenshot_date(camera_path)
        details["last_video_time"] = get_latest_video_date(video_path)
        details["snapshot_only"] = is_snapshot_url(details.get("url", ""))
    return templates


def get_templates_sorted_by_last_caption_time():
    """Return templates sorted by ``last_caption_time`` newest first."""

    manager = TemplateManager()
    return manager.get_templates_by_last_caption_time()


def get_template(name):
    """Return template details for ``name`` using :class:`TemplateManager`."""

    name = validate_template_name(name)
    if name is None:
        return None

    manager = TemplateManager()
    return manager.get_template(name)


def save_template(name: str, template_data) -> bool:
    """Save a template and ensure storage directories exist.

    Parameters
    ----------
    name : str
        Template name to create or update.
    template_data : dict
        Attributes used when saving the template.

    Returns
    -------
    bool
        ``True`` when the template is persisted, ``False`` if the
        provided name fails validation.
    """

    name = validate_template_name(name)
    if name is None:
        return False

    manager = TemplateManager()
    manager.save_template(name, template_data)
    screenshot_full_path = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(name))
    os.makedirs(screenshot_full_path, exist_ok=True)
    video_full_path = os.path.join(VIDEO_DIRECTORY, secure_filename(name))
    os.makedirs(video_full_path, exist_ok=True)

    return True


def delete_template(name: str) -> bool:
    """Delete ``name`` from the database and remove associated files.

    Parameters
    ----------
    name : str
        Template identifier.

    Returns
    -------
    bool
        ``True`` if the template was removed, otherwise ``False``.
    """

    name = validate_template_name(name)
    if name is None:
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
    """Return template details by ``template_id`` if valid."""

    if not isinstance(template_id, int) or template_id <= 0:
        return {}

    manager = TemplateManager()
    return manager.get_template_by_id(template_id)


def get_screenshots_for_template(name: str) -> list:
    """Return a list of screenshot filenames for ``name``.

    Parameters
    ----------
    name : str
        Template name used when locating the screenshot directory.

    Returns
    -------
    list
        Up to 100 screenshot filenames sorted newest first.
    """

    name = validate_template_name(name)
    if name is None:
        return []
    if not os.path.exists(os.path.join(SCREENSHOT_DIRECTORY, name)):
        return []
    screenshots = [
        f
        for f in os.listdir(os.path.join(SCREENSHOT_DIRECTORY, name))
        if f.startswith(name)
        and f.endswith(".png")
        and ".tmp" not in f
        and ".partial" not in f
    ]

    try:
        sorted_screenshots = sorted(
            screenshots,
            key=lambda x: datetime.strptime(
                x[len(name) + 1 : -4].replace("_blank", ""), "%Y%m%d%H%M%S"
            ),
            reverse=True,
        )
    except Exception as e:
        logging.error("sorting issue %s", e)
        return []

    return sorted_screenshots[:100]


def get_videos_for_template(name: str):
    """Return a list of video filenames for ``name``.

    Parameters
    ----------
    name : str
        Template name whose video directory will be inspected.

    Returns
    -------
    list
        Up to 10 video filenames sorted newest first.
    """

    name = validate_template_name(name)
    if name is None:
        return []
    if not os.path.exists(os.path.join(VIDEO_DIRECTORY, name)):
        return []
    videos = [
        f
        for f in os.listdir(os.path.join(VIDEO_DIRECTORY, name))
        if (f.startswith(name) or f.startswith("final_")) and f.endswith(".mp4")
    ]
    sorted_videos = sorted(
        videos,
        reverse=True,
    )
    return sorted_videos[:10]


def get_screenshot_count(name: str) -> int:
    """Return the number of stored screenshots for ``name``."""

    name = validate_template_name(name)
    if name is None:
        return 0
    screenshot_path = os.path.join(SCREENSHOT_DIRECTORY, name)
    if not os.path.exists(screenshot_path):
        return 0
    return len([f for f in os.listdir(screenshot_path) if f.endswith(".png")])


def get_video_count(name: str) -> int:
    """Return the number of stored videos for ``name``."""

    name = validate_template_name(name)
    if name is None:
        return 0
    video_path = os.path.join(VIDEO_DIRECTORY, name)
    if not os.path.exists(video_path):
        return 0
    return len([f for f in os.listdir(video_path) if f.endswith(".mp4")])


def get_storage_usage(name: str) -> str:
    """Calculate disk usage for ``name``.

    Parameters
    ----------
    name : str
        Template name to measure on disk.

    Returns
    -------
    str
        Human readable size of all screenshots and videos.
    """

    name = validate_template_name(name)
    if name is None:
        return "0 B"
    screenshot_path = os.path.join(SCREENSHOT_DIRECTORY, name)
    video_path = os.path.join(VIDEO_DIRECTORY, name)
    total_size = 0

    for path in [screenshot_path, video_path]:
        if os.path.exists(path):
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)

    # Convert to human-readable format
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if total_size < 1024.0:
            break
        total_size /= 1024.0
    return f"{total_size:.1f} {unit}"


def get_storage_usage_bytes(name: str) -> int:
    """Return total storage used for ``name`` in bytes."""

    name = validate_template_name(name)
    if name is None:
        return 0

    screenshot_path = os.path.join(SCREENSHOT_DIRECTORY, name)
    video_path = os.path.join(VIDEO_DIRECTORY, name)
    total_size = 0

    for path in [screenshot_path, video_path]:
        if os.path.exists(path):
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)

    return total_size


def record_llm_usage(name: str, tokens: int) -> None:
    """Record token usage for ``name`` with a timestamp.

    The data format was originally a single cumulative integer. This now stores
    a list of timestamped entries while remaining backward compatible.
    """
    name = validate_template_name(name)
    if name is None or tokens <= 0:
        return

    os.makedirs(os.path.dirname(LLM_USAGE_PATH), exist_ok=True)
    try:
        with open(LLM_USAGE_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        data = {}

    entry = data.get(name)
    if isinstance(entry, int):
        entry = {"total": entry, "entries": []}
    elif isinstance(entry, list):
        entry = {"total": sum(e.get("tokens", 0) for e in entry), "entries": entry}
    elif not isinstance(entry, dict):
        entry = {"total": 0, "entries": []}

    entry["entries"].append(
        {"time": datetime.utcnow().strftime("%Y-%m-%d"), "tokens": int(tokens)}
    )
    entry["total"] += int(tokens)
    data[name] = entry

    try:
        with open(LLM_USAGE_PATH, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error("Failed to record LLM usage: %s", e)


def get_llm_response_count(name: str) -> int:
    """Return the number of LLM responses recorded for ``name``.

    Counts how many response entries are stored for the template in
    ``LLM_USAGE_PATH``. The function is tolerant of the existing data format
    where token usage may be recorded as either a list of entries or a single
    cumulative integer.
    """

    name = validate_template_name(name)
    if name is None:
        return 0

    if not os.path.exists(LLM_USAGE_PATH):
        return 0

    try:
        with open(LLM_USAGE_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return 0

    entry = data.get(name, [])
    if isinstance(entry, dict):
        entry = entry.get("entries", [])
    if isinstance(entry, list):
        return len(entry)
    if isinstance(entry, int):
        return 1 if entry > 0 else 0
    return 0


def get_llm_cost_estimate(
    name: str, start_date: str | None = None, end_date: str | None = None
) -> str:
    """Estimate LLM cost for ``name`` within an optional date range."""

    name = validate_template_name(name)
    if name is None:
        return "$0.00"

    try:
        with open(LLM_USAGE_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        data = {}

    entry = data.get(name)
    tokens = 0
    if isinstance(entry, dict) and "entries" in entry:
        entries = entry.get("entries", [])
        sd = datetime.fromisoformat(start_date).date() if start_date else None
        ed = datetime.fromisoformat(end_date).date() if end_date else None
        for e in entries:
            try:
                dt = datetime.fromisoformat(e.get("time", "")).date()
            except Exception:
                continue
            if sd and dt < sd:
                continue
            if ed and dt > ed:
                continue
            tokens += int(e.get("tokens", 0))
        if not start_date and not end_date:
            tokens = entry.get("total", tokens)
    else:
        tokens = entry if isinstance(entry, int) else 0

    cost = tokens * LLM_COST_PER_TOKEN
    return f"${cost:.2f}"


def get_llm_token_usage(name: str) -> int:
    """Return the total tokens recorded for ``name``."""

    name = validate_template_name(name)
    if name is None:
        return 0

    if not os.path.exists(LLM_USAGE_PATH):
        return 0

    try:
        with open(LLM_USAGE_PATH, "r") as f:
            data = json.load(f)
    except Exception:
        return 0

    entry = data.get(name, 0)
    if isinstance(entry, list):
        total = 0
        for val in entry:
            if isinstance(val, int):
                total += val
            elif isinstance(val, dict) and "tokens" in val:
                try:
                    total += int(val["tokens"])
                except Exception:
                    continue
        return total
    if isinstance(entry, int):
        return entry
    return 0


def update_last_screenshot_time(name: str) -> None:
    """Set ``last_screenshot_time`` to now and clear ``offline_since``."""
    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template:
            template.last_screenshot_time = datetime.utcnow().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            template.offline_since = ""
            template.capture_failed = False
            session.commit()
    finally:
        session.close()


def mark_offline(name: str) -> None:
    """Record the time a camera was first detected offline."""
    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template and not template.offline_since:
            template.offline_since = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            session.commit()
    finally:
        session.close()


def set_capture_failed(name: str, failed: bool) -> None:
    """Set ``capture_failed`` flag for ``name``."""
    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template:
            template.capture_failed = bool(failed)
            session.commit()
    finally:
        session.close()


def _update_scheduler_job(name: str, frequency: int) -> None:
    """Reschedule the APScheduler job for ``name`` if it exists.

    The scheduler uses the template's frequency to determine the interval. Any
    update should remove the old job and create a new one so changes apply
    immediately.
    """

    from . import scheduling  # Imported here to avoid circular dependency

    try:
        scheduling.scheduler.remove_job(name)
    except Exception:
        pass

    seconds = 60 * int(frequency)
    try:
        scheduling.scheduler.add_job(
            func=scheduling.update_camera,
            trigger="interval",
            seconds=seconds,
            args=[name, {}],
            id=name,
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)
