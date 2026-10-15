import socket

from src.security import SecurityError, decrypt_packet, encrypt_packet, has_session, new_session, purge_buffer


class UniversalRelay:
    """The middle man. It starts at rest; a handshake opens a session (and a fresh encryption key) on a port that is really listening; relay_to_engine moves one command to an
    engine encrypted and brings the answer back; the session then ends and the key is destroyed (stateless: nothing is remembered between commands)."""

    def __init__(self, host="127.0.0.1", timeout=0.5):
        self.active_session = None
        self.host = host
        self.timeout = timeout

    def establish_handshake(self, port_id, ai_signature):
        """Agnostic connection: opens a session if the port is live (something is listening on it). The AI's identity is not examined. -> True/False."""
        if not ai_signature:
            return False
        if self._is_port_live(port_id):
            new_session()
            self.active_session = {"port": port_id, "signature": ai_signature}
            return True
        return False

    def relay_to_engine(self, command, target_engine):
        """Encrypts the command, hands it to target_engine.execute(), decrypts the answer (which the engine must have encrypted with encrypt_packet), then ends the session.
        -> the decrypted answer, or None when there is no session. SecurityError if the engine's answer is not from this session; the session is ended either way."""
        if not self.active_session or not has_session():
            return None
        try:
            response = target_engine.execute(encrypt_packet(command))
            return decrypt_packet(response)                          # decrypted BEFORE the key is destroyed
        finally:
            self.purge()

    def purge(self):
        """Stateless wipe: the session and its key are gone."""
        self.active_session = None
        purge_buffer()

    def _is_port_live(self, port_id):
        """True when a TCP connection to host:port is accepted right now. A port that is not a valid number is not live."""
        if isinstance(port_id, bool) or not isinstance(port_id, int) or not 0 < port_id < 65536:
            return False
        try:
            with socket.create_connection((self.host, port_id), timeout=self.timeout):
                return True
        except OSError:
            return False
