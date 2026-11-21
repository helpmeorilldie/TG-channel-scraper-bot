import os
from cryptography.fernet import Fernet
from config import DATA_DIR

KEYFILE = os.path.join(DATA_DIR, ".session_key")

def _load() -> bytes:
    env = os.environ.get("SESSION_ENC_KEY", "").strip()
    if env:
        return env.encode()
    if os.path.exists(KEYFILE):
        with open(KEYFILE, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    fd = os.open(KEYFILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    print(f"generated {KEYFILE} — back this file up, sessions die without it")
    return key

_f = Fernet(_load())

def enc(s: str) -> bytes: return _f.encrypt(s.encode())
def dec(b: bytes) -> str: return _f.decrypt(b).decode()
