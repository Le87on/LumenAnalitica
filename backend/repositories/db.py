from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from backend.core.config import settings

DB_PATH = Path(settings.database_path).resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()



def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                last_login_at TEXT,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                event_type TEXT NOT NULL,
                detail TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                usuario TEXT NOT NULL,
                rol TEXT NOT NULL,
                evento TEXT NOT NULL,
                objetivo TEXT,
                detalle TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                nombre TEXT NOT NULL,
                documento TEXT NOT NULL,
                segmento TEXT NOT NULL,
                score_total REAL NOT NULL,
                decision TEXT NOT NULL,
                score_credito REAL NOT NULL,
                score_cheques REAL NOT NULL,
                score_patrimonial REAL NOT NULL,
                deuda_total_pesos REAL NOT NULL,
                peor_situacion INTEGER NOT NULL,
                cheques_rechazados INTEGER NOT NULL,
                patrimonio_estimado REAL NOT NULL,
                liquidez_inmediata REAL NOT NULL,
                observaciones TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.commit()



def write_audit(usuario: str, rol: str, evento: str, objetivo: str = "", detalle: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO auditoria (fecha, usuario, rol, evento, objetivo, detalle)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                usuario,
                rol,
                evento,
                objetivo,
                detalle,
            ),
        )
        conn.commit()
