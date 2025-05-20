import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
SUPERADMIN_USERNAME = os.getenv("SUPERADMIN_USERNAME")
SUPERADMIN_PASSWORD_ENCRYPTED = os.getenv("SUPERADMIN_PASSWORD_ENCRYPTED")

if not all([ENCRYPTION_KEY, SUPERADMIN_USERNAME, SUPERADMIN_PASSWORD_ENCRYPTED]):
    raise ValueError("Missing required environment variables")

try:
    fernet = Fernet(ENCRYPTION_KEY.encode())
except Exception as e:
    raise ValueError(f"Invalid encryption key: {e}")


