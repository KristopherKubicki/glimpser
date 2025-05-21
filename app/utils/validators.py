# app/utils/validators.py

from werkzeug.utils import secure_filename


def validate_template_name(template_name: str):
    """Return sanitized template name if valid, otherwise ``None``."""
    if template_name is None or not isinstance(template_name, str):
        return None

    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-." 
    )
    if not all(char in allowed_chars for char in template_name):
        return None

    if len(template_name) == 0 or len(template_name) > 32:
        return None

    if template_name[0] in "-_." or template_name[-1] in "-_.":
        return None
    if ".." in template_name:
        return None
    if "--" in template_name:
        return None
    if "__" in template_name:
        return None

    sanitized_name = secure_filename(template_name)
    if sanitized_name != template_name:
        return None

    return sanitized_name
