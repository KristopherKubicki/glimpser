from cryptography.fernet import Fernet
from app.config import ENCRYPTION_KEY


def encrypt_data(data):
    if not isinstance(data, bytes):
        data = str(data).encode()
    f = Fernet(ENCRYPTION_KEY)
    return f.encrypt(data)


def decrypt_data(encrypted_data):
    f = Fernet(ENCRYPTION_KEY)
    return f.decrypt(encrypted_data).decode()
