"""Encrypted local OAuth refresh-token vault for a private single-user gateway.

The 32-byte AES-GCM key MUST come from an independently secured VPS secret.
Do not store the key next to the encrypted vault or in Git/CI artifacts.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import stat

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_AAD = b"agency-calendar-oauth-vault-v1"


class VaultUnavailable(RuntimeError):
    pass


class EncryptedFileVault:
    """Atomic, authenticated secret file. For one writer on a private volume."""

    def __init__(self, path, *, key):
        self.path = Path(path)
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("vault requires a separate 256-bit key")
        self._cipher = AESGCM(key)

    def _check_parent(self):
        parent = self.path.parent
        try:
            meta = parent.lstat()
            if (not stat.S_ISDIR(meta.st_mode)
                    or meta.st_uid != os.getuid()
                    or stat.S_IMODE(meta.st_mode) & 0o077):
                raise VaultUnavailable("private vault directory unavailable")
        except FileNotFoundError:
            raise VaultUnavailable("private vault directory unavailable") from None
        if self.path.is_symlink():
            raise VaultUnavailable("vault symlink prohibited")

    def save(self, value):
        self._check_parent()
        if (not isinstance(value, dict)
                or not isinstance(value.get("refresh_token"), str)
                or not value["refresh_token"]
                or not isinstance(value.get("scopes"), list)
                or any(not isinstance(v, str) for v in value["scopes"])):
            raise ValueError("invalid vault payload")
        body = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
        if len(body) > 4096:
            raise ValueError("vault payload exceeds limit")
        nonce = secrets.token_bytes(12)
        record = json.dumps({
            "v": 1,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(
                self._cipher.encrypt(nonce, body, _AAD)).decode("ascii"),
        }, separators=(",", ":")).encode()
        tmp = self.path.parent / (".vault-" + secrets.token_hex(12))
        fd = None
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(record)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                existing = self.path.lstat()
                if (not stat.S_ISREG(existing.st_mode)
                        or existing.st_uid != os.getuid()
                        or stat.S_IMODE(existing.st_mode) & 0o077):
                    raise VaultUnavailable("existing vault permissions unsafe")
            self._check_parent()
            os.replace(tmp, self.path)
            dir_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if fd is not None:
                os.close(fd)
            if tmp.exists():
                tmp.unlink()

    def load(self):
        self._check_parent()
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        except OSError:
            raise VaultUnavailable("vault unavailable") from None
        try:
            meta = os.fstat(fd)
            if (not stat.S_ISREG(meta.st_mode)
                    or meta.st_uid != os.getuid()
                    or stat.S_IMODE(meta.st_mode) & 0o077
                    or meta.st_size > 8192):
                raise VaultUnavailable("vault access rejected")
            with os.fdopen(fd, "rb") as stream:
                fd = None
                data = stream.read(8193)
            doc = json.loads(data)
            if doc.get("v") != 1:
                raise ValueError()
            nonce = base64.b64decode(doc["nonce"], validate=True)
            cipher = base64.b64decode(doc["ciphertext"], validate=True)
            body = self._cipher.decrypt(nonce, cipher, _AAD)
            value = json.loads(body)
            if (not isinstance(value, dict)
                    or not isinstance(value.get("refresh_token"), str)
                    or not isinstance(value.get("scopes"), list)):
                raise ValueError()
            return value
        except Exception as error:
            if isinstance(error, VaultUnavailable):
                raise
            raise VaultUnavailable("vault unavailable or invalid") from None
        finally:
            if fd is not None:
                os.close(fd)
