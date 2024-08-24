import re
from werkzeug.utils import secure_filename


def validate_template_name(template_name: str) -> str | None:
    if template_name is None or not isinstance(template_name, str):
        return None

    # Strict whitelist of allowed characters
    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
    )

    # Check if all characters are in the allowed set
    if not all(char in allowed_chars for char in template_name):
        return None

    # Check length
    if len(template_name) == 0 or len(template_name) > 32:
        return None

    # Ensure the name doesn't start or end with a dash, underscore, or dot
    if template_name[0] in "-_." or template_name[-1] in "-_.":
        return None

    # Check for consecutive special characters
    if ".." in template_name or "--" in template_name or "__" in template_name:
        return None

    # Use secure_filename as an additional safety measure
    sanitized_name = secure_filename(template_name)

    # Ensure secure_filename didn't change the name (which would indicate it found something suspicious)
    if sanitized_name != template_name:
        return None

    return sanitized_name


def allowed_filename(filename: str) -> bool:
    if ".." in filename:
        return False

    if not re.match(r"^[a-zA-Z0-9\.\-_]+$", filename):
        return False

    return True
