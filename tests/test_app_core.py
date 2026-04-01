import sqlite3

import app


def test_clean_doc_and_validar_identificacion():
    assert app.clean_doc('20-12345678-9') == '20123456789'
    assert app.validar_identificacion('20-12345678-9') is True
    assert app.validar_identificacion('123') is False


def test_parse_cheques_rechazados_aggregates_values():
    raw = {
        'causales': [
            {
                'causal': 'SIN FONDOS',
                'entidades': [
                    {
                        'entidad': '001',
                        'detalle': [
                            {'monto': 1000, 'estadoMulta': 'IMPAGA'},
                            {'monto': 2500, 'estadoMulta': 'PAGA'},
                        ],
                    }
                ],
            }
        ]
    }
    resumen = app.parse_cheques_rechazados(raw)
    assert resumen.cantidad_total == 2
    assert resumen.monto_total == 3500.0
    assert resumen.multa_impaga is True


def test_authenticate_user_uses_password_hash_verification(tmp_path, monkeypatch):
    db_path = tmp_path / 'test_credit.db'
    monkeypatch.setattr(app, 'DB_PATH', db_path)

    conn = app.get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        'INSERT INTO usuarios (username, password_hash, rol, activo) VALUES (?, ?, ?, 1)',
        ('analista', app.hash_password('secreto123'), 'admin'),
    )
    conn.commit()
    conn.close()

    ok = app.authenticate_user('analista', 'secreto123')
    bad = app.authenticate_user('analista', 'invalida')

    assert ok == {'username': 'analista', 'rol': 'admin'}
    assert bad is None
