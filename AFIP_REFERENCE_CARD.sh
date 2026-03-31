#!/bin/bash
# AFIP Configuration Quick Reference Card
# Guarda este archivo para consulta rápida

cat <<'EOF'

╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║            🔐 LumenAnalitica - Configuración AFIP                         ║
║                        Quick Reference Card                               ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝


┌─────────────────────────────────────────────────────────────────────────────┐
│                   MODO 1: DESARROLLO (LOCAL)                               │
└─────────────────────────────────────────────────────────────────────────────┘

PASO 1: GENERAR CERTIFICADOS AUTOFIRMADOS
─────────────────────────────────────────

  $ python setup_afip_dev.py --cuit 20123456789

  ✓ Genera clave privada RSA (2048 bits)
  ✓ Crea certificado autofirmado (válido 365 días)
  ✓ Establece permisos correctos (600/644)
  ✓ Crea/actualiza archivo .env
  ✓ Salida visual con confirmaciones

  Resultado:
    ./afip_certs/
    ├── certificate.crt (certificado X.509)
    └── private_key.pem (clave privada)


PASO 2: VERIFICAR CONFIGURACIÓN
───────────────────────────────

  $ python verify_afip_certificates.py

  ✓ Valida certificados  
  ✓ Verifica fechas de vencimiento
  ✓ Comprueba compatibilidad cert/key
  ✓ Chequea permisos de archivos
  
  Salida esperada:
    ✅ Todos los certificados están correctamente configurados


PASO 3: INSTALAR DEPENDENCIAS
──────────────────────────────

  $ pip install -r requirements.txt

  Incluye:
    - streamlit
    - afip.py
    - python-dotenv
    - pandas
    - requests
    - reportlab


PASO 4: INICIAR APLICACIÓN
──────────────────────────

  $ streamlit run app.py

  ✓ Abre http://localhost:8501
  ✓ AFIP en modo staging
  ✓ Consultas a AFIP funcionan


═════════════════════════════════════════════════════════════════════════════


┌─────────────────────────────────────────────────────────────────────────────┐
│              MODO 2: PRODUCCIÓN (SERVIDOR)                                  │
└─────────────────────────────────────────────────────────────────────────────┘

PASO 1: OBTENER CERTIFICADOS REALES
────────────────────────────────────

  1. Ir a: https://www.afip.gob.ar
  2. Login con Clave Fiscal (CUIT + contraseña)
  3. Sección: Servicios REST → Solicitar Certificado
  4. Seguir el proceso de AFIP
  5. Descargar:
     - certificate.crt (firmado por AFIP)
     - private_key.pem (generado localmente)


PASO 2: PREPARAR SERVIDOR
─────────────────────────

  # En tu servidor (SSH):
  
  $ sudo mkdir -p /etc/lumenanalitica/afip_certs
  $ sudo chmod 700 /etc/lumenanalitica/afip_certs

  # Copiar certificados (desde máquina local):
  
  $ scp certificate.crt usuario@servidor.com:/tmp/
  $ scp private_key.pem usuario@servidor.com:/tmp/

  # En servidor:
  
  $ sudo mv /tmp/certificate.crt /etc/lumenanalitica/afip_certs/
  $ sudo mv /tmp/private_key.pem /etc/lumenanalitica/afip_certs/
  
  # Permisos correctos:
  
  $ sudo chmod 644 /etc/lumenanalitica/afip_certs/certificate.crt
  $ sudo chmod 600 /etc/lumenanalitica/afip_certs/private_key.pem
  $ sudo chown -R www-data:www-data /etc/lumenanalitica/afip_certs


PASO 3: CONFIGURAR VARIABLES DE ENTORNO
────────────────────────────────────────

  # En servidor:
  
  $ sudo nano /etc/lumenanalitica/.env

  Contenido:
  ─────────
  AFIP_CUIT=20123456789
  AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt
  AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem
  AFIP_PRODUCTION=true
  AFIP_API_TIMEOUT=30
  AFIP_MAX_RETRIES=2
  DB_PATH=/var/lib/lumenanalitica/creditdb.sqlite
  LOG_FILE=/var/log/lumenanalitica/app.log
  LOG_LEVEL=INFO


PASO 4: VERIFICAR EN SERVIDOR
──────────────────────────────

  $ python verify_afip_certificates.py

  ✓ Valida certificados REALES
  ✓ Verifica fechas (no vencidos)
  ✓ Comprueba compatibilidad
  
  Salida esperada:
    ✅ Todos los certificados están correctamente configurados


PASO 5: INICIAR APLICACIÓN EN PRODUCCIÓN
─────────────────────────────────────────

  # Opción A: Systemd service (recomendado)
  
  /etc/systemd/system/lumenanalitica.service
  ──────────────────────────────────────────
  [Unit]
  Description=LumenAnalitica Credit Analysis
  After=network.target

  [Service]
  Type=simple
  User=www-data
  WorkingDirectory=/var/www/lumenanalitica
  Environment="PATH=/var/www/lumenanalitica/venv/bin"
  ExecStart=/var/www/lumenanalitica/venv/bin/streamlit run app.py
  Restart=always
  RestartSec=10

  [Install]
  WantedBy=multi-user.target

  # Activar:
  $ sudo systemctl enable lumenanalitica
  $ sudo systemctl start lumenanalitica


  # Opción B: Docker (alternative)
  
  $ docker run -d \
    --name lumenanalitica \
    -p 8501:8501 \
    -v /etc/lumenanalitica/afip_certs:/etc/lumenanalitica/afip_certs:ro \
    -e AFIP_CUIT=20123456789 \
    -e AFIP_PRODUCTION=true \
    -e AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt \
    -e AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem \
    lumenanalitica:latest


═════════════════════════════════════════════════════════════════════════════


┌─────────────────────────────────────────────────────────────────────────────┐
│                     COMANDOS MÁS ÚTILES                                     │
└─────────────────────────────────────────────────────────────────────────────┘

Ver estado de configuración:
──────────────────────────
  $ python config.py

Ver fechas de certificados:
──────────────────────────
  $ openssl x509 -in afip_certs/certificate.crt -noout -dates

Verificar cert y key coinciden:
──────────────────────────────
  $ openssl x509 -noout -modulus -in cert.crt | openssl md5
  $ openssl rsa -noout -modulus -in key.pem | openssl md5
  # Deben dar el mismo resultado

Hacer backup de certificados:
─────────────────────────────
  $ tar -czf afip_backup.tar.gz /etc/lumenanalitica/afip_certs/

Ver logs:
────────
  $ tail -f /var/log/lumenanalitica/app.log

Monitorear vencimiento (en crontab):
────────────────────────────────────
  0 0 * * * python /scripts/check_cert_expiry.py


═════════════════════════════════════════════════════════════════════════════


┌─────────────────────────────────────────────────────────────────────────────┐
│                    🔐 CHECKLIST DE SEGURIDAD                               │
└─────────────────────────────────────────────────────────────────────────────┘

DESARROLLO:
  ✓ Certificados autofirmados OK
  ✓ No están en Git (en .gitignore)
  ✓ .env has permisos restrictivos
  ✓ python-dotenv instalado

PRODUCCIÓN:
  ✓ Certificados reales de AFIP
  ✓ En /etc/lumenanalitica/afip_certs/
  ✓ Permisos 600 en clave privada
  ✓ Permisos 644 en certificado
  ✓ Propietario es www-data/usuario de app
  ✓ .env NO está en Git
  ✓ Backup de clave privada hecho
  ✓ Fecha de vencimiento registrada
  ✓ Logs auditados configurados
  ✓ Monitoreo de expiración activo


═════════════════════════════════════════════════════════════════════════════


┌─────────────────────────────────────────────────────────────────────────────┐
│                  ESTRUCTURA DE DIRECTORIOS FINAL                            │
└─────────────────────────────────────────────────────────────────────────────┘

LOCAL (DESARROLLO):
─────────────────

  LumenAnalitica/
  ├── app.py
  ├── config.py ← Configuración AFIP centralizada
  ├── setup_afip_dev.py ← Generator de certificados
  ├── verify_afip_certificates.py ← Validador
  ├── requirements.txt (actualizado)
  ├── .env ← Variables de entorno (NO en Git)
  ├── .env.example ← Template
  ├── .gitignore (actualizado)
  ├── afip_certs/ ← Certificados locales
  │   ├── certificate.crt
  │   └── private_key.pem
  ├── AFIP_QUICK_START.md ← Guía rápida
  ├── AFIP_PRODUCTION_SETUP.md ← Guía completa
  └── AFIP_ARCHITECTURE.md ← Documentación técnica


SERVIDOR (PRODUCCIÓN):
─────────────────────

  /etc/lumenanalitica/
  ├── .env (configuración AFIP)
  └── afip_certs/
      ├── certificate.crt (644)
      └── private_key.pem (600)

  /var/lib/lumenanalitica/
  └── creditdb.sqlite

  /var/log/lumenanalitica/
  ├── app.log
  └── afip.log


═════════════════════════════════════════════════════════════════════════════


📞 SOPORTE Y RECURSOS
─────────────────────

  Quick Start:        cat AFIP_QUICK_START.md
  Full Setup:        cat AFIP_PRODUCTION_SETUP.md
  Architecture:      cat AFIP_ARCHITECTURE.md
  Config Reference:  python config.py
  
  AFIP Portal:       https://www.afip.gob.ar
  afip.py Docs:      https://github.com/piieza/afip.py
  OpenSSL Docs:      https://www.openssl.org/docs/

═════════════════════════════════════════════════════════════════════════════
Última actualización: 2026-03-31 | Version: 1.0
═════════════════════════════════════════════════════════════════════════════

EOF
