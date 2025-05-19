from app.config import fernet

def verify_password(plain_password: str, encrypted_password: str) -> bool:
    try:
        decrypted_password = fernet.decrypt(encrypted_password.encode()).decode()
        return plain_password == decrypted_password
    except Exception:
        return False