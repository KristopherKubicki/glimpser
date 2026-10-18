"""Manage screenshot templates stored in the SQLite database.

The :class:`TemplateManager` exposes CRUD operations for template records
and tracks token usage for LLM captions.  It validates paths and names to
avoid security issues and lazily initializes the underlying database on
first use.
"""

import json
import logging
import os
import re
import shutil
from datetime import datetime
from functools import lru_cache

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import validates
from werkzeug.utils import secure_filename

from app.config import SCREENSHOT_DIRECTORY, VIDEO_DIRECTORY
from app.utils import db
from app.utils.db import commit_with_retry

from .validators import is_bool_string, to_bool, validate_template_name
from .video_details import get_latest_screenshot_date, get_latest_video_date

# Keep aliases for backward compatibility and testing mocks
SessionLocal = db.SessionLocal
init_db = db.init_db
ensure_columns = db.ensure_columns
Base = db.Base

LLM_USAGE_PATH = "data/llm_usage.json"
LLM_COST_PER_TOKEN = 0.005 / 1000  # OpenAI pricing example


def parse_canonical_screenshot_timestamp(name: str, filename: str) -> datetime | None:
    """Return the capture time encoded in a canonical screenshot filename.

    Canonical still frames are named ``<camera>_<YYYYmmddHHMMSS>.png`` with an
    optional ``_blank`` suffix. Sidecars such as ``last_motion.png`` or
    ``.orig.png`` should never participate in latest-frame selection.
    """

    valid_name = validate_template_name(name)
    if valid_name is None:
        return None

    if not filename.endswith(".png") or filename.endswith(".orig.png"):
        return None

    prefix = f"{valid_name}_"
    if not filename.startswith(prefix):
        return None

    timestamp = filename[len(prefix) : -4]
    if timestamp.endswith("_blank"):
        timestamp = timestamp[: -len("_blank")]
    if len(timestamp) != 14 or not timestamp.isdigit():
        return None

    try:
        return datetime.strptime(timestamp, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def sort_canonical_screenshot_filenames(
    name: str, filenames: list[str], reverse: bool = False
) -> list[str]:
    """Return canonical screenshot filenames sorted by embedded capture time."""

    canonical = []
    for filename in filenames:
        captured_at = parse_canonical_screenshot_timestamp(name, filename)
        if captured_at is None:
            continue
        canonical.append((captured_at, filename))

    canonical.sort(key=lambda item: (item[0], item[1]), reverse=reverse)
    return [filename for _, filename in canonical]


def is_snapshot_url(url: str) -> bool:
    """Return ``True`` when ``url`` points to a still image endpoint."""

    if not url:
        return False
    url = url.lower()
    return (
        url.endswith((".jpg", ".jpeg", ".png")) or "snapshot" in url or "picture" in url
    )


class Template(db.Base):
    """Database model describing a camera template."""

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
    last_capture_status = Column(String, default="")
    last_capture_message = Column(Text, default="")
    last_capture_status_time = Column(String, default="")
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
    thumbnail = Column(String, default="")
    groups = Column(String, default="")
    baseline_caption = Column(Text, default="")
    invert = Column(Boolean, default=False)
    dark = Column(Boolean, default=False)
    disable_autocrop = Column(Boolean, default=False)
    headless = Column(Boolean, default=True)
    stealth = Column(Boolean, default=False)
    browser = Column(Boolean, default=False)
    stabilize_mode = Column(String, default="")
    capture_rotate_degrees = Column(Integer, default=0)
    capture_crop_roi = Column(String, default="")
    lens_correction_spec = Column(String, default="")
    horizon_level_mode = Column(String, default="")
    horizon_level_roi = Column(String, default="")
    night_enhance_mode = Column(String, default="")
    deflicker_mode = Column(String, default="")
    source_template = Column(String, default="")
    burst_enhance_mode = Column(String, default="")
    burst_enhance_profile = Column(String, default="")
    burst_enhance_roi = Column(String, default="")
    composite_view_mode = Column(String, default="")
    composite_view_spec = Column(Text, default="")
    camera_latitude = Column(Float, default=None)
    camera_longitude = Column(Float, default=None)
    camera_elevation_m = Column(Float, default=None)
    camera_location_label = Column(String, default="")
    camera_location_accuracy = Column(String, default="")
    camera_location_evidence = Column(Text, default="")
    camera_location_private = Column(Boolean, default=False)
    view_target_latitude = Column(Float, default=None)
    view_target_longitude = Column(Float, default=None)
    view_target_label = Column(String, default="")
    view_description = Column(Text, default="")
    view_direction = Column(String, default="")
    view_bearing_degrees = Column(Float, default=None)
    view_pitch_degrees = Column(Float, default=None)
    view_roll_degrees = Column(Float, default=None)
    view_horizontal_fov_degrees = Column(Float, default=None)
    view_vertical_fov_degrees = Column(Float, default=None)
    view_mount_height = Column(String, default="")
    view_pose_confidence = Column(String, default="")
    view_pose_evidence = Column(Text, default="")
    view_staticness = Column(String, default="")
    view_metadata = Column(Text, default="")
    view_metadata_version = Column(Integer, default=0)
    view_metadata_history = Column(Text, default="")
    view_metadata_updated = Column(String, default="")
    livecaption = Column(Boolean, default=False)
    danger = Column(Boolean, default=False)
    ptz_enabled = Column(Boolean, default=False)
    ptz_service = Column(String, default="")
    ptz_profile_token = Column(String, default="")
    ptz_profile_name = Column(String, default="")
    ptz_presets = Column(Text, default="")
    ptz_vendor_driver = Column(String, default="")
    private_camera = Column(Boolean, default=False)
    motion = Column(Float, default=0.2)
    rollback_frames = Column(Integer, default=0)
    event_buffer_enabled = Column(Boolean, default=False)
    event_buffer_profile = Column(String, default="")
    event_buffer_fps = Column(Integer, default=1)
    event_buffer_seconds = Column(Integer, default=120)
    event_buffer_width = Column(Integer, default=640)
    event_buffer_pre_seconds = Column(Integer, default=8)
    event_buffer_post_seconds = Column(Integer, default=6)
    event_buffer_format = Column(String, default="gif")
    event_buffer_backoff_seconds = Column(Integer, default=300)
    last_ret = None

    @validates("frequency")
    def validate_frequency(self, key, frequency):
        """Validate ``frequency`` is within a reasonable range."""

        if frequency > 525600:
            raise ValueError("Frequency cannot be greater than 525600 (1 year)")
        return frequency

    @validates("timeout")
    def validate_timeout(self, key, timeout):
        """Ensure ``timeout`` is positive and not longer than frequency."""

        if timeout < 1:
            logging.warning("negative timeout")
            timeout = 10
        if timeout >= float(self.frequency) * 60:
            timeout = float(self.frequency) * 60
            raise ValueError(f"timeout calculation error {timeout} {self.frequency}")
        return timeout

    @validates("popup_xpath", "dedicated_xpath")
    def validate_xpath(self, key, xpath):
        """Verify XPath expressions start with ``//``."""

        if xpath and not xpath.startswith("//"):
            raise ValueError(f"{key} must start with '//'")
        return xpath

    @validates("object_confidence")
    def validate_object_confidence(self, key, confidence):
        """Check object detection confidence is between 0 and 1."""

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
        """Initialize the database and upgrade missing columns."""

        init_db()
        # Ensure the templates table exists even when Base has been reloaded
        Template.__table__.create(db.engine, checkfirst=True)
        # Automatically add newer columns when upgrading from older versions
        ensure_columns(
            "templates",
            [
                ("capture_failed", "BOOLEAN", "0"),
                ("last_capture_status", "VARCHAR(32)", "''"),
                ("last_capture_message", "TEXT", "''"),
                ("last_capture_status_time", "TEXT", "''"),
                ("auth_username", "VARCHAR(255)", "''"),
                ("auth_password", "VARCHAR(255)", "''"),
                ("thumbnail", "VARCHAR(255)", "''"),
                ("baseline_caption", "TEXT", "''"),
                ("disable_autocrop", "BOOLEAN", "0"),
                ("ptz_enabled", "BOOLEAN", "0"),
                ("ptz_service", "VARCHAR(255)", "''"),
                ("ptz_profile_token", "VARCHAR(255)", "''"),
                ("ptz_profile_name", "VARCHAR(255)", "''"),
                ("ptz_presets", "TEXT", "''"),
                ("ptz_vendor_driver", "VARCHAR(255)", "''"),
                ("private_camera", "BOOLEAN", "0"),
                ("stabilize_mode", "VARCHAR(32)", "''"),
                ("capture_rotate_degrees", "INTEGER", "0"),
                ("capture_crop_roi", "VARCHAR(255)", "''"),
                ("lens_correction_spec", "VARCHAR(255)", "''"),
                ("horizon_level_mode", "VARCHAR(32)", "''"),
                ("horizon_level_roi", "VARCHAR(255)", "''"),
                ("night_enhance_mode", "VARCHAR(32)", "''"),
                ("deflicker_mode", "VARCHAR(32)", "''"),
                ("source_template", "VARCHAR(32)", "''"),
                ("burst_enhance_mode", "VARCHAR(32)", "''"),
                ("burst_enhance_profile", "VARCHAR(32)", "''"),
                ("burst_enhance_roi", "VARCHAR(255)", "''"),
                ("composite_view_mode", "VARCHAR(32)", "''"),
                ("composite_view_spec", "TEXT", "''"),
                ("camera_latitude", "REAL", "NULL"),
                ("camera_longitude", "REAL", "NULL"),
                ("camera_elevation_m", "REAL", "NULL"),
                ("camera_location_label", "VARCHAR(255)", "''"),
                ("camera_location_accuracy", "VARCHAR(32)", "''"),
                ("camera_location_evidence", "TEXT", "''"),
                ("camera_location_private", "BOOLEAN", "0"),
                ("view_target_latitude", "REAL", "NULL"),
                ("view_target_longitude", "REAL", "NULL"),
                ("view_target_label", "VARCHAR(255)", "''"),
                ("view_description", "TEXT", "''"),
                ("view_direction", "VARCHAR(64)", "''"),
                ("view_bearing_degrees", "REAL", "NULL"),
                ("view_pitch_degrees", "REAL", "NULL"),
                ("view_roll_degrees", "REAL", "NULL"),
                ("view_horizontal_fov_degrees", "REAL", "NULL"),
                ("view_vertical_fov_degrees", "REAL", "NULL"),
                ("view_mount_height", "VARCHAR(128)", "''"),
                ("view_pose_confidence", "VARCHAR(32)", "''"),
                ("view_pose_evidence", "TEXT", "''"),
                ("view_staticness", "VARCHAR(32)", "''"),
                ("view_metadata", "TEXT", "''"),
                ("view_metadata_version", "INTEGER", "0"),
                ("view_metadata_history", "TEXT", "''"),
                ("view_metadata_updated", "TEXT", "''"),
                ("event_buffer_enabled", "BOOLEAN", "0"),
                ("event_buffer_profile", "VARCHAR(32)", "''"),
                ("event_buffer_fps", "INTEGER", "1"),
                ("event_buffer_seconds", "INTEGER", "120"),
                ("event_buffer_width", "INTEGER", "640"),
                ("event_buffer_pre_seconds", "INTEGER", "8"),
                ("event_buffer_post_seconds", "INTEGER", "6"),
                ("event_buffer_format", "VARCHAR(16)", "'gif'"),
                ("event_buffer_backoff_seconds", "INTEGER", "300"),
            ],
        )

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
            result = {}
            for template in templates:
                # Templates without a name are not addressable via the UI or
                # scheduler; treat them as invalid and ignore.
                if not template.name:
                    continue
                data = template.__dict__.copy()
                data.pop("_sa_instance_state", None)
                result[template.name] = data
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
                # Always set the name on create. Some callers only pass it via
                # the `name` argument (not inside `details`).
                template = Template(name=name)
                session.add(template)
                ldelta = True
            else:
                ldelta = False

            # Caption/health writes must not reset capture cadence. Only
            # configuration changes require replacing a scheduler job.
            reschedule = ldelta

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
            if details.get("frequency") in {"", None}:
                details["frequency"] = template.frequency or default_frequency
            if details.get("timeout") in {"", None}:
                details["timeout"] = template.timeout or default_timeout
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
                            value = int(value or 0)
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
                        elif key == "view_bearing_degrees":
                            if value in {None, ""}:
                                value = None
                            else:
                                value = float(value)
                                if not 0 <= value < 360:
                                    raise ValueError(
                                        "View bearing degrees must be >= 0 and < 360"
                                    )
                        elif key in {"camera_latitude", "view_target_latitude"}:
                            if value in {None, ""}:
                                value = None
                            else:
                                value = float(value)
                                if not -90 <= value <= 90:
                                    raise ValueError(
                                        "Latitude must be >= -90 and <= 90"
                                    )
                        elif key in {"camera_longitude", "view_target_longitude"}:
                            if value in {None, ""}:
                                value = None
                            else:
                                value = float(value)
                                if not -180 <= value <= 180:
                                    raise ValueError(
                                        "Longitude must be >= -180 and <= 180"
                                    )
                        elif key == "camera_elevation_m":
                            if value in {None, ""}:
                                value = None
                            else:
                                value = float(value)
                        elif key in {"camera_location_label", "view_target_label"}:
                            value = str(value or "").strip()
                            if len(value) > 255:
                                raise ValueError("Location label is too long")
                        elif key in {"camera_location_evidence", "view_pose_evidence"}:
                            value = str(value or "").strip()
                            if len(value) > 2000:
                                raise ValueError("Evidence is too long")
                        elif key == "camera_location_accuracy":
                            value = str(value or "").strip().lower()
                            if value == "unknown":
                                value = ""
                            if value not in {
                                "",
                                "exact",
                                "approximate",
                                "site",
                                "region",
                                "source",
                            }:
                                raise ValueError("Invalid camera location accuracy")
                        elif key in {
                            "view_pitch_degrees",
                            "view_roll_degrees",
                            "view_horizontal_fov_degrees",
                            "view_vertical_fov_degrees",
                        }:
                            if value in {None, ""}:
                                value = None
                            else:
                                value = float(value)
                                if key == "view_pitch_degrees" and not (
                                    -90 <= value <= 90
                                ):
                                    raise ValueError(
                                        "View pitch degrees must be >= -90 and <= 90"
                                    )
                                if key == "view_roll_degrees" and not (
                                    -180 <= value <= 180
                                ):
                                    raise ValueError(
                                        "View roll degrees must be >= -180 and <= 180"
                                    )
                                if key == "view_horizontal_fov_degrees" and not (
                                    0 < value <= 360
                                ):
                                    raise ValueError(
                                        "Horizontal FOV degrees must be > 0 and <= 360"
                                    )
                                if key == "view_vertical_fov_degrees" and not (
                                    0 < value <= 180
                                ):
                                    raise ValueError(
                                        "Vertical FOV degrees must be > 0 and <= 180"
                                    )
                        elif key == "view_mount_height":
                            value = str(value or "").strip()
                            if len(value) > 128:
                                raise ValueError("View mount height is too long")
                        elif key == "view_pose_confidence":
                            value = str(value or "").strip().lower()
                            if value == "unknown":
                                value = ""
                            if value not in {"", "estimated", "operator", "calibrated"}:
                                raise ValueError("Invalid view pose confidence")
                        elif key == "view_staticness":
                            value = str(value or "").strip().lower()
                            if value == "unknown":
                                value = ""
                            if value not in {
                                "",
                                "static",
                                "slight_drift",
                                "drifting",
                                "ptz",
                                "rotating",
                                "composite",
                            }:
                                raise ValueError("Invalid view staticness")
                        elif key == "view_metadata":
                            value = str(value or "").strip()
                            if value:
                                json.loads(value)
                        elif key == "view_metadata_history":
                            value = str(value or "").strip()
                            if value:
                                json.loads(value)
                        elif key == "view_metadata_version":
                            value = int(value or 0)
                            if value < 0:
                                raise ValueError("View metadata version must be >= 0")
                        elif key in ["popup_xpath", "dedicated_xpath"]:
                            if value and not value.startswith("//"):
                                raise ValueError(f"{key} must start with '//'")
                        elif key in {
                            "stealth",
                            "headless",
                            "dark",
                            "invert",
                            "disable_autocrop",
                            "browser",
                            "livecaption",
                            "danger",
                            "ptz_enabled",
                            "private_camera",
                            "camera_location_private",
                            "capture_failed",
                        }:
                            if isinstance(value, str):
                                if is_bool_string(value):
                                    value = to_bool(value)
                                else:
                                    logging.debug(
                                        "Unrecognized boolean string for %s",
                                        key,
                                    )
                                    continue
                            elif isinstance(value, bool):
                                pass
                            elif isinstance(value, int) and value in (0, 1):
                                value = bool(value)
                            else:
                                logging.debug("Unrecognized boolean value for %s", key)
                                continue
                    except (TypeError, ValueError) as e:
                        # Log the validation error and return False
                        logging.warning("Validation error: %s %s %s", str(e), name, key)
                        return False

                    # check to make sure a change actually occurred
                    if getattr(template, key) != value:
                        setattr(template, key, value)
                        ldelta = True
                        if key not in {
                            "last_caption",
                            "last_ret",
                            "last_caption_time",
                            "last_motion_caption",
                            "last_motion_time",
                            "last_screenshot_time",
                            "last_video_time",
                            "capture_failed",
                            "offline_since",
                            "last_capture_status",
                            "last_capture_message",
                            "last_capture_status_time",
                        }:
                            reschedule = True
            if ldelta is True:
                session.commit()
                # Recreate the scheduler job so the new settings take effect
                if reschedule:
                    _update_scheduler_job(name, template.frequency)
            return True
        except Exception as e:
            logging.error("Error saving template: %s", str(e))
            return False
        finally:
            session.close()

    def _rename_prefixed_entries(
        self, directory: str, old_name: str, new_name: str
    ) -> None:
        """Rename files in ``directory`` that start with ``old_name``.

        Template names are embedded in screenshot and video filenames, so a
        template rename has to update both the directory name and the stored
        file prefixes. This keeps history, clip listings, and derived views
        addressable after the rename.
        """

        if not os.path.isdir(directory):
            return

        for entry_name in os.listdir(directory):
            if not entry_name.startswith(old_name):
                continue
            src = os.path.join(directory, entry_name)
            dst = os.path.join(directory, f"{new_name}{entry_name[len(old_name) :]}")
            if os.path.exists(dst):
                raise ValueError(f"Destination already exists: {dst}")
            os.replace(src, dst)

    def _refresh_latest_screenshot_symlink(self, directory: str) -> None:
        """Refresh ``latest_camera.png`` in ``directory`` after a rename."""

        if not os.path.isdir(directory):
            return

        png_files = [
            f
            for f in os.listdir(directory)
            if f.endswith(".png")
            and f != "latest_camera.png"
            and os.path.isfile(os.path.join(directory, f))
        ]
        symlink_path = os.path.join(directory, "latest_camera.png")
        if os.path.lexists(symlink_path):
            os.unlink(symlink_path)
        if not png_files:
            return

        camera_name = os.path.basename(os.path.normpath(directory))
        png_files = sort_canonical_screenshot_filenames(camera_name, png_files)
        if not png_files:
            return

        latest_name = png_files[-1]
        os.symlink(os.path.join(directory, latest_name), symlink_path)

    def _rename_template_storage(self, old_name: str, new_name: str) -> None:
        """Move template storage and rename filename prefixes.

        Screenshots, videos, and the per-template ``latest_camera.png`` symlink
        all key off the template name. This helper keeps the on-disk structure
        coherent before the scheduler starts writing to the new name.
        """

        old_shot_dir = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(old_name))
        new_shot_dir = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(new_name))
        old_video_dir = os.path.join(VIDEO_DIRECTORY, secure_filename(old_name))
        new_video_dir = os.path.join(VIDEO_DIRECTORY, secure_filename(new_name))

        if os.path.exists(new_shot_dir) or os.path.exists(new_video_dir):
            raise ValueError(f"Storage already exists for {new_name}")

        if os.path.isdir(old_shot_dir):
            shutil.move(old_shot_dir, new_shot_dir)
            self._rename_prefixed_entries(new_shot_dir, old_name, new_name)
            self._refresh_latest_screenshot_symlink(new_shot_dir)

        if os.path.isdir(old_video_dir):
            shutil.move(old_video_dir, new_video_dir)
            self._rename_prefixed_entries(new_video_dir, old_name, new_name)

    def rename_template(self, old_name: str, new_name: str) -> str:
        """Rename a template and its on-disk assets.

        Parameters
        ----------
        old_name : str
            Existing template name.
        new_name : str
            New validated template name.

        Returns
        -------
        str
            The final stored template name.
        """

        old_name = validate_template_name(old_name)
        new_name = validate_template_name(new_name)
        if old_name is None or new_name is None:
            raise ValueError("Invalid template name")
        if old_name == new_name:
            return old_name

        session = self.get_session()
        try:
            template = session.query(Template).filter_by(name=old_name).first()
            if template is None:
                raise ValueError(f"Template not found: {old_name}")
            if session.query(Template).filter_by(name=new_name).first() is not None:
                raise ValueError(f"Template already exists: {new_name}")

            self._rename_template_storage(old_name, new_name)
            template.name = new_name
            for dependent in (
                session.query(Template).filter_by(source_template=old_name).all()
            ):
                dependent.source_template = new_name
            commit_with_retry(session)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return new_name

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


@lru_cache(maxsize=1)
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


def clear_template_cache() -> None:
    """Clear cached template data."""

    get_templates.cache_clear()


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


def save_caption_metadata(name: str, details: dict) -> bool:
    """Update captions on an existing source without rewriting its configuration.

    Capture jobs hold snapshots of template settings. Revalidating or saving
    that entire snapshot can reject legacy metadata or overwrite operator edits.
    """
    name = validate_template_name(name)
    if name is None:
        return False
    session = SessionLocal()
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template is None:
            return False
        for key in (
            "last_caption",
            "last_caption_time",
            "last_motion_caption",
            "last_motion_time",
        ):
            if key not in details:
                continue
            value = details[key]
            if value is None:
                value = ""
            if not isinstance(value, str):
                return False
            setattr(template, key, value)
        session.commit()
        clear_template_cache()
        return True
    except Exception as error:
        session.rollback()
        logging.error(
            "Caption metadata save failed for %s: %s", name, type(error).__name__
        )
        return False
    finally:
        session.close()


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
    success = manager.save_template(name, template_data)
    if not success:
        return False

    clear_template_cache()
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
        clear_template_cache()
        screenshot_full_path = os.path.join(SCREENSHOT_DIRECTORY, secure_filename(name))
        if os.path.exists(screenshot_full_path) and os.path.isdir(screenshot_full_path):
            shutil.rmtree(screenshot_full_path)
        video_full_path = os.path.join(VIDEO_DIRECTORY, secure_filename(name))
        if os.path.exists(video_full_path) and os.path.isdir(video_full_path):
            shutil.rmtree(video_full_path)
    return success


def rename_template(old_name: str, new_name: str) -> str:
    """Rename a template and clear the cached template map."""

    manager = TemplateManager()
    renamed = manager.rename_template(old_name, new_name)
    clear_template_cache()
    return renamed


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
    return sort_canonical_screenshot_filenames(name, screenshots, reverse=True)[:100]


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

    def _sort_key(filename: str) -> int:
        match = re.search(r"(\d+)(?=\.mp4$)", filename)
        return int(match.group(1)) if match else -1

    sorted_videos = sorted(videos, key=_sort_key, reverse=True)
    if "last_video.mp4" not in sorted_videos:
        sorted_videos.append("last_video.mp4")
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
        with open(LLM_USAGE_PATH) as f:
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
        with open(LLM_USAGE_PATH) as f:
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
        with open(LLM_USAGE_PATH) as f:
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
    elif isinstance(entry, list):
        sd = datetime.fromisoformat(start_date).date() if start_date else None
        ed = datetime.fromisoformat(end_date).date() if end_date else None
        if entry and isinstance(entry[0], dict):
            for e in entry:
                try:
                    dt = datetime.fromisoformat(e.get("time", "")).date()
                except Exception:
                    continue
                if sd and dt < sd:
                    continue
                if ed and dt > ed:
                    continue
                tokens += int(e.get("tokens", 0))
        elif not start_date and not end_date:
            for e in entry:
                try:
                    tokens += int(e)
                except Exception:
                    continue
    elif isinstance(entry, dict):
        tokens = int(entry.get("total", 0))
    else:
        tokens = entry if isinstance(entry, int) else 0

    cost = tokens * LLM_COST_PER_TOKEN
    return f"${cost:.3f}"


def get_llm_cost_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    group: str | None = None,
) -> tuple[list[dict[str, object]], int, str, int]:
    """Return LLM usage totals and overall cost within an optional date range.

    When ``group`` is provided, only templates belonging to that group are
    included in the summary.
    """

    try:
        with open(LLM_USAGE_PATH) as f:
            data = json.load(f)
    except Exception:
        data = {}

    summary = []
    total_tokens = 0
    total_calls = 0
    sd = datetime.fromisoformat(start_date).date() if start_date else None
    ed = datetime.fromisoformat(end_date).date() if end_date else None

    allowed_names: set[str] | None = None
    if group:
        tmpl = TemplateManager().get_templates()
        allowed_names = {
            name
            for name, details in tmpl.items()
            if group in [g.strip() for g in details.get("groups", "").split(",")]
        }
    for name in sorted(data):
        if allowed_names is not None and name not in allowed_names:
            continue
        entry = data.get(name, 0)
        tokens = 0
        calls = 0
        if isinstance(entry, dict) and "entries" in entry:
            entries = entry.get("entries", [])
            for e in entries:
                try:
                    dt = datetime.fromisoformat(e.get("time", "")).date()
                except Exception:
                    continue
                if sd and dt < sd:
                    continue
                if ed and dt > ed:
                    continue
                try:
                    tokens += int(e.get("tokens", 0))
                    calls += 1
                except Exception:
                    continue
            if not start_date and not end_date:
                tokens = entry.get("total", tokens)
                calls = len(entries)
        elif isinstance(entry, list):
            tokens = sum(int(t) for t in entry)
            calls = len(entry)
        elif isinstance(entry, dict):
            tokens = int(entry.get("total", 0))
            calls = len(entry.get("entries", []))
        elif isinstance(entry, int):
            tokens = entry
            calls = 1 if entry > 0 else 0
        total_tokens += tokens
        total_calls += calls
        cost = tokens * LLM_COST_PER_TOKEN
        summary.append(
            {
                "name": name,
                "tokens": tokens,
                "cost": f"${cost:.3f}",
                "calls": calls,
            }
        )

    total_cost = total_tokens * LLM_COST_PER_TOKEN
    return summary, total_tokens, f"${total_cost:.3f}", total_calls


def group_cost_summary(
    summary: list[dict[str, object]], top: int = 10
) -> list[dict[str, object]]:
    """Return ``summary`` sorted by cost with smaller entries grouped."""

    def _cost_val(entry: dict[str, object]) -> float:
        try:
            return float(str(entry.get("cost", "$0")).replace("$", ""))
        except Exception:
            return 0.0

    rows = sorted(summary, key=_cost_val, reverse=True)
    if len(rows) <= top:
        return rows

    keep = rows[: top - 1]
    other_tokens = sum(r.get("tokens", 0) for r in rows[top - 1 :])
    other_cost = sum(_cost_val(r) for r in rows[top - 1 :])
    other_calls = sum(r.get("calls", 0) for r in rows[top - 1 :])
    keep.append(
        {
            "name": "Other",
            "tokens": other_tokens,
            "cost": f"${other_cost:.3f}",
            "calls": other_calls,
        }
    )
    return keep


def update_last_screenshot_time(name: str, captured_at: datetime | None = None) -> None:
    """Record the validated image acquisition time and clear capture failure state."""
    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    changed = False
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            template.last_screenshot_time = (
                captured_at.strftime("%Y-%m-%d %H:%M:%S")
                if captured_at is not None
                else now
            )
            template.last_capture_status = "fresh"
            template.last_capture_message = ""
            template.last_capture_status_time = now
            template.offline_since = ""
            template.capture_failed = False
            commit_with_retry(session)
            changed = True
    finally:
        session.close()
    if changed:
        clear_template_cache()


def set_capture_stale(name: str, reason: str = "stale_previous_frame") -> None:
    """Record that capture kept the last good frame instead of writing a new one."""
    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    changed = False
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            template.capture_failed = False
            template.offline_since = ""
            template.last_capture_status = "stale_ok"
            template.last_capture_message = str(reason or "stale_previous_frame")[:500]
            template.last_capture_status_time = now
            commit_with_retry(session)
            changed = True
    finally:
        session.close()
    if changed:
        clear_template_cache()


def mark_offline(name: str) -> None:
    """Record the time a camera was first detected offline."""
    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    changed = False
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template and not template.offline_since:
            template.offline_since = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            session.commit()
            changed = True
    finally:
        session.close()
    if changed:
        clear_template_cache()


def clear_offline(name: str) -> None:
    """Clear the offline status for ``name`` without changing capture times."""

    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    changed = False
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template and template.offline_since:
            template.offline_since = ""
            session.commit()
            changed = True
    finally:
        session.close()
    if changed:
        clear_template_cache()


def set_capture_failed(name: str, failed: bool, reason: str | None = None) -> None:
    """Set ``capture_failed`` flag for ``name``."""
    name = validate_template_name(name)
    if name is None:
        return

    manager = TemplateManager()
    session = manager.get_session()
    changed = False
    try:
        template = session.query(Template).filter_by(name=name).first()
        if template:
            template.capture_failed = bool(failed)
            template.last_capture_status = (
                "failed" if failed else template.last_capture_status
            )
            if failed:
                template.last_capture_status_time = datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                template.last_capture_message = str(reason or "")[:500]
            if not failed:
                template.offline_since = ""
                template.last_capture_message = ""
            session.commit()
            changed = True
    finally:
        session.close()
    if changed:
        clear_template_cache()


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
            func=scheduling.schedule_camera_capture,
            trigger="interval",
            seconds=seconds,
            args=[name, {}, min(120, max(10, seconds - 5))],
            executor=scheduling.camera_executor(get_template(name) or {}),
            max_instances=1,
            coalesce=True,
            # Match startup scheduling: brief executor delays must not drop a capture.
            misfire_grace_time=max(30, seconds),
            id=name,
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)
