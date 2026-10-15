"""security.py - real encryption for packets that pass through the link (Fernet: AES-128-CBC with an HMAC, from the `cryptography` package).

A session key is made when a session starts (new_session) and destroyed when it is purged (purge_buffer). encrypt_packet / decrypt_packet use the CURRENT session key; without one they
raise instead of passing the data through. A packet encrypted in one session cannot be read in the next, and a changed packet is detected on decrypt."""
import gc
import secrets

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:                                           # the link must refuse to move data rather than move it unprotected
    Fernet = None
    InvalidToken = Exception

_session = {"fernet": None}


class SecurityError(RuntimeError):
    """No session key, no cryptography package, or a packet that does not decrypt."""


def new_session():
    """Starts a fresh session with its own random key (the old key, if any, is dropped). -> True."""
    if Fernet is None:
        raise SecurityError("the 'cryptography' package is not installed: pip install cryptography")
    _session["fernet"] = Fernet(Fernet.generate_key())
    return True


def has_session():
    return _session["fernet"] is not None


def encrypt_packet(data):
    """str -> an opaque token (str). SecurityError if there is no session."""
    if _session["fernet"] is None:
        raise SecurityError("no session key: start a session (a handshake) before sending")
    return _session["fernet"].encrypt(str(data).encode()).decode()


def decrypt_packet(payload):
    """token -> str. SecurityError for a packet from another session or one that was altered."""
    if _session["fernet"] is None:
        raise SecurityError("no session key: nothing can be decrypted")
    try:
        return _session["fernet"].decrypt(payload.encode() if isinstance(payload, str) else payload).decode()
    except InvalidToken as e:
        raise SecurityError("the packet is not from this session or was altered") from e


def purge_buffer():
    """Destroys the session key and asks the interpreter to free what it can. Packets of the ended session can no longer be read."""
    _session["fernet"] = None
    gc.collect()


class SecureGatekeeper:
    """One session's lock: its own key, created on construction and gone after close()."""

    def __init__(self):
        self._session_key = secrets.token_bytes(32)

    def sign(self, message):
        import hashlib
        import hmac
        return hmac.new(self._session_key, str(message).encode(), hashlib.sha256).hexdigest()

    def verify(self, message, signature):
        import hmac
        return hmac.compare_digest(self.sign(message), str(signature))

    def close(self):
        self._session_key = b""
