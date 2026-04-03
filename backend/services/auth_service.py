from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from passlib.context import CryptContext

from backend.core.config import settings
from backend.repositories.db import get_conn

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def hash_password(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except Exception:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            120_000,
        )
        return f"pbkdf2_sha256${salt}${digest.hex()}"



def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        try:
            scheme, salt, digest_hex = password_hash.split("$", 2)
            if scheme != "pbkdf2_sha256":
                return False
        except ValueError:
            return False
        test_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            120_000,
        ).hex()
        return hmac.compare_digest(test_digest, digest_hex)



def _record_auth_event(username: str, event_type: str, detail: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO auth_events (username, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
            (username, event_type, detail, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()



def ensure_bootstrap_user() -> None:
    username = settings.bootstrap_user.strip()
    password = settings.bootstrap_password.strip()
    role = settings.bootstrap_role.strip() or "admin"
    if not username or not password:
        return

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM usuarios WHERE username = ?",
            (username,),
        ).fetchone()[0]
        if int(existing) == 0:
            conn.execute(
                "INSERT INTO usuarios (username, password_hash, rol, activo) VALUES (?, ?, ?, 1)",
                (username, hash_password(password), role),
            )
            conn.commit()



def authenticate_user(username: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    username = (username or "").strip()
    password = password or ""

    if not username or not password:
        return None, "Usuario y contraseña son obligatorios."

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT username, rol, password_hash, activo, failed_attempts, locked_until
            FROM usuarios
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

        if not row:
            _record_auth_event(username, "login_failure", "usuario_inexistente")
            return None, "Usuario o contraseña incorrectos."

        username_db, rol, password_hash, activo, failed_attempts, locked_until_raw = row

        if int(activo) != 1:
            _record_auth_event(username, "login_denied", "usuario_inactivo")
            return None, "Cuenta inactiva."

        if locked_until_raw:
            locked_until = datetime.fromisoformat(str(locked_until_raw))
            if datetime.now() < locked_until:
                _record_auth_event(username, "login_denied", "cuenta_bloqueada")
                return None, f"Cuenta bloqueada hasta {locked_until.strftime('%H:%M:%S')}."

        if verify_password(password, str(password_hash)):
            conn.execute(
                "UPDATE usuarios SET failed_attempts = 0, locked_until = NULL, last_login_at = ? WHERE username = ?",
                (datetime.now().isoformat(timespec="seconds"), username),
            )
            conn.commit()
            _record_auth_event(username, "login_success", "credenciales_validas")
            return {"username": username_db, "rol": rol}, None

        updated_attempts = int(failed_attempts or 0) + 1
        if updated_attempts >= MAX_LOGIN_ATTEMPTS:
            lock_until = datetime.now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            conn.execute(
                "UPDATE usuarios SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                (updated_attempts, lock_until.isoformat(timespec="seconds"), username),
            )
            conn.commit()
            _record_auth_event(username, "login_lockout", f"intentos={updated_attempts}")
            return None, f"Cuenta bloqueada por {LOGIN_LOCKOUT_MINUTES} minutos."

        conn.execute(
            "UPDATE usuarios SET failed_attempts = ? WHERE username = ?",
            (updated_attempts, username),
        )
        conn.commit()
        _record_auth_event(username, "login_failure", f"intentos={updated_attempts}")
        return None, "Usuario o contraseña incorrectos."
