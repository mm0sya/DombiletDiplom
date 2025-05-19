from cryptography.fernet import Fernet
import base64

# Генерируем ключ шифрования
key = Fernet.generate_key()
fernet = Fernet(key)

# Пароль superadmin
superadmin_password = "admin123"  # Замените на реальный пароль

# Шифруем пароль
encrypted_password = fernet.encrypt(superadmin_password.encode()).decode()

# Выводим ключ и зашифрованный пароль
print(f"Encryption Key: {key.decode()}")
print(f"Encrypted Password: {encrypted_password}")