import re

def validate_password(password: str) -> bool:
    """Проверка пароля: ≥8 символов, минимум 1 заглавная латинская буква, 1 специальный символ."""
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password):
        return False
    if not re.match(r"^[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{}|;:,.<>?]*$", password):
        return False
    return True