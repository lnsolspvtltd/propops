from cryptography.fernet import Fernet
import os

def encrypt(plaintext: str) -> str:
    """Encrypt plaintext using Fernet."""
    key = os.getenv('FERNET_KEY')
    if not key:
        raise ValueError("FERNET_KEY environment variable is missing.")
    
    f = Fernet(key)
    encrypted = f.encrypt(plaintext.encode())
    return encrypted.decode()

def decrypt(ciphertext: str) -> str:
    """Decrypt ciphertext using Fernet."""
    key = os.getenv('FERNET_KEY')
    if not key:
        raise ValueError("FERNET_KEY environment variable is missing.")
    
    f = Fernet(key)
    decrypted = f.decrypt(ciphertext.encode())
    return decrypted.decode()