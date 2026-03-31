# 🔐 Certificados AFIP - Guía Rápida

## 📝 Resumen Ejecutivo

Este proyecto incluye integración completa con **AFIP (Administración Federal de Ingresos Públicos)** para validación fiscal de solicitantes de crédito.

**Modo actual:** Desarrollo (se puede cambiar a producción)

---

## 🚀 Start Rápido (Desarrollo)

### 1️⃣ Generar certificados de prueba

```bash
# Ejecutar setup automático (genera certificados autofirmados)
python setup_afip_dev.py --cuit 20123456789
```

✅ Esto:
- Genera clave privada y certificado autofirmado
- Crea/actualiza el archivo `.env`
- Configura permisos correctamente

### 2️⃣ Verificar instalación

```bash
# Valida que todos los certificados estén correctamente configurados
python verify_afip_certificates.py
```

### 3️⃣ Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4️⃣ Iniciar aplicación

```bash
streamlit run app.py
```

---

## 🏭 Producción - Paso a Paso

### Paso 1: Obtener Certificados Reales

```bash
# 1. Ir a https://www.afip.gob.ar
# 2. Login con Clave Fiscal
# 3. Solicitar "Certificado de Clave Fiscal"
# 4. Descargar archivos:
#    - certificate.crt (certificado firmado por AFIP)
#    - private_key.pem (clave privada generada localmente)
```

### Paso 2: Deploy del Servidor

```bash
# En tu servidor de producción:

# Crear directorio seguro
sudo mkdir -p /etc/lumenanalitica/afip_certs
sudo chmod 700 /etc/lumenanalitica/afip_certs

# Copiar certificados (sCLI, no por Git!)
scp certificate.crt usuario@servidor:/etc/lumenanalitica/afip_certs/
scp private_key.pem usuario@servidor:/etc/lumenanalitica/afip_certs/

# Ajustar permisos
ssh usuario@servidor
sudo chmod 600 /etc/lumenanalitica/afip_certs/*
sudo chown -R www-data:www-data /etc/lumenanalitica/afip_certs
```

### Paso 3: Configurar Variables de Entorno

```bash
# Crear .env en servidor
sudo nano /etc/lumenanalitica/.env
```

Contenido:

```env
AFIP_CUIT=20123456789
AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt
AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem
AFIP_PRODUCTION=true
AFIP_API_TIMEOUT=30
DB_PATH=/var/lib/lumenanalitica/creditdb.sqlite
LOG_FILE=/var/log/lumenanalitica/app.log
```

### Paso 4: Verificar Certificados en Producción

```bash
# Ejecutar verificador
ssh usuario@servidor
cd /path/to/lumenanalitica
python verify_afip_certificates.py
```

✅ Debe mostrar: "Todos los certificados están correctamente configurados"

### Paso 5: Docker (Opcional)

```bash
# Build
docker build -t lumenanalitica:prod .

# Run con volumen de certificados
docker run -d \
  --name lumenanalitica \
  -p 8501:8501 \
  -v /etc/lumenanalitica/afip_certs:/etc/lumenanalitica/afip_certs:ro \
  -v /var/lib/lumenanalitica:/var/lib/lumenanalitica \
  -v /var/log/lumenanalitica:/var/log/lumenanalitica \
  -e AFIP_CUIT=20123456789 \
  -e AFIP_PRODUCTION=true \
  -e AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt \
  -e AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem \
  lumenanalitica:prod
```

---

## 📂 Estructura de Archivos

```
LumenAnalitica/
├── app.py                          # Aplicación principal
├── config.py                       # ✨ Configuración centralizada
├── requirements.txt                # Dependencias Python
├── .env                            # Variables de entorno (NO en Git)
├── .env.example                    # ✨ Template .env
├── setup_afip_dev.py               # ✨ Script setup para desarrollo
├── verify_afip_certificates.py     # ✨ Validador de certificados
├── AFIP_PRODUCTION_SETUP.md        # ✨ Guía completa
├── afip_certs/                     # Directorio de certificados (desarrollo)
│   ├── certificate.crt
│   └── private_key.pem
└── data/
    └── creditdb.sqlite
```

- ✨ = Nuevo en esta integración

---

## 🔍 Verificar Configuración Actual

```bash
# Ver estado de configuración
python -c "from config import AFIPConfig; print(AFIPConfig.get_status())"
```

Salida esperada:

```
{
    'cuit': '20***789',
    'production': False,
    'cert_configured': True,
    'key_configured': True,
    'ready': True
}
```

---

## 🎯 Cambiar a Producción

### En .env:

```diff
- AFIP_PRODUCTION=false
+ AFIP_PRODUCTION=true

- AFIP_CERT_PATH=./afip_certs/certificate.crt
+ AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt

- AFIP_KEY_PATH=./afip_certs/private_key.pem
+ AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem
```

Luego:

```bash
python verify_afip_certificates.py
```

---

## ⚠️ Seguridad

### ✅ Hacer:

- ✅ Guardar claves privadas con permisos `600`
- ✅ Usar variables de entorno (nunca hardcodear paths)
- ✅ Hacer backup de claves privadas (en lugar seguro)
- ✅ Rotar certificados cada 1-2 años
- ✅ Monitorear fecha de vencimiento

### ❌ NO Hacer:

- ❌ Commitear `.env` a Git
- ❌ Usar certificados de desarrollo en producción
- ❌ Compartir claves privadas
- ❌ Almacenar certificados en `/tmp`
- ❌ Establecer permisos públicos en claves

---

## 🐛 Troubleshooting

### Error: "Certificate not found"

```bash
# Verificar rutas
cd /workspaces/LumenAnalitica
ls -la afip_certs/
python verify_afip_certificates.py
```

### Error: "SSL: CERTIFICATE_VERIFY_FAILED"

```bash
# Certificado vencido o fecha del sistema incorrecta
date
openssl x509 -in afip_certs/certificate.crt -noout -dates
```

### Error: "Key and certificate don't match"

```bash
# Regenerar certificados
rm -rf afip_certs/
python setup_afip_dev.py --cuit 20123456789
```

---

## 📚 Archivos de Referencia

| Archivo | Propósito |
|---------|-----------|
| `config.py` | Configuración AFIP centralizada |
| `.env.example` | Template de variables de entorno |
| `setup_afip_dev.py` | Generar certificados autofirmados |
| `verify_afip_certificates.py` | Validar certificados |
| `AFIP_PRODUCTION_SETUP.md` | Guía completa (75+ pasos) |

---

## 🔗 Enlaces Útiles

- [AFIP REST Services](https://www.afip.gob.ar/genericos/restservice)
- [Documentación afip.py](https://github.com/piieza/afip.py)
- [OpenSSL Manual](https://www.openssl.org/docs/)
- [Estructura X.509](https://en.wikipedia.org/wiki/X.509)

---

## ✅ Checklist Producción

- [ ] Certificado AFIP real descargado
- [ ] Clave privada generada/almacenada seguramente
- [ ] Directorio `/etc/lumenanalitica/afip_certs` creado
- [ ] Permisos 600 en claves privadas
- [ ] Variables `.env` configuradas
- [ ] `python verify_afip_certificates.py` → ✓
- [ ] Pruebas en staging completadas
- [ ] Certificado NO vencido
- [ ] Backup de clave privada hecho
- [ ] Logs auditados configurados
- [ ] Documentación del proceso guardada

---

**¿Preguntas?** Revisar [AFIP_PRODUCTION_SETUP.md](./AFIP_PRODUCTION_SETUP.md) para guía completa.
