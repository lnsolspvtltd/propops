"""Fernet symmetric encryption for storing IMAP/SMTP passwords."""
import os

from cryptography.fernet import Fernet


def _key() -> bytes:
    k = os.environ.get("FERNET_KEY", "")
    if not k:
        raise RuntimeError("FERNET_KEY environment variable is not set")
    return k.encode()


def encrypt(plaintext: str) -> str:
    """Encrypt a string with Fernet. Key from FERNET_KEY env var."""
    return Fernet(_key()).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    return Fernet(_key()).decrypt(ciphertext.encode()).decode()
