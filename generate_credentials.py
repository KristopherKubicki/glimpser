import secrets
from werkzeug.security import generate_password_hash

def generate_credentials():
    secret_key = secrets.token_hex(16)
    username = input("Enter the username for login: ")
    password = input("Enter the password for login: ")
    password_hash = generate_password_hash(password)

    with open('auth.py', 'w') as config_file:
        config_file.write(f"\nSECRET_KEY = '{secret_key}'\n")
        config_file.write(f"USER_NAME = '{username}'\n")
        config_file.write(f"USER_PASSWORD_HASH = '{password_hash}'\n")
        config_file.write(f"API_KEY = '" + secrets.token_hex(32) + "'")
        config_file.write(f"CHATGPT_KEY = ''") # TODO

if __name__ == '__main__':
    generate_credentials()

