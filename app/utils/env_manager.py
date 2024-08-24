import os
from dotenv import load_dotenv


def load_env_variables():
    """
    Load environment variables from .env file
    """
    dotenv_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    load_dotenv(dotenv_path)


def get_env_variable(var_name, default=None):
    """
    Get an environment variable or return a default value
    """
    return os.getenv(var_name, default)
