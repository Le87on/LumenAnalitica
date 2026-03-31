# Configuración de Certificados AFIP para Producción

## 📋 Requisitos Previos

1. **CUIT de la empresa** - El número de CUIT de tu razón social
2. **Clave Fiscal AFIP** - Acceso a [https://www.afip.gob.ar](https://www.afip.gob.ar)
3. **Certificado Digital X.509** - Seguir el proceso de AFIP para obtenerlo
4. **OpenSSL** - Para procesar certificados (ya incluido en el sistema)

---

## 🔐 Paso 1: Obtener el Certificado AFIP

### 1.1 Acceder a AFIP
- Ve a [https://www.afip.gob.ar/genericos/restservice](https://www.afip.gob.ar/genericos/restservice)
- Inicia sesión con tu CUIT y Clave Fiscal
- Selecciona **"Solicitar nuevo Certificado de Clave Fiscal"**

### 1.2 Generar CSR (Certificate Signing Request)

**Opción A: Generar en tu servidor (Recomendado)**

```bash
# Crear clave privada (2048 bits)
openssl genrsa -out /etc/lumenanalitica/afip_private_key.pem 2048

# Generar CSR (Certificate Signing Request)
openssl req -new \
  -key /etc/lumenanalitica/afip_private_key.pem \
  -out /etc/lumenanalitica/afip_cert.csr \
  -subj "/C=AR/ST=Buenos Aires/L=Buenos Aires/O=Tu Empresa/CN=tu-empresa.com"
```

**Opción B: Generar en la interfaz de AFIP**
- AFIP puede generar la CSR por ti
- Te enviará un archivo `.csr` que debes guardar

### 1.3 Obtener Certificado Firmado

1. Envía el CSR a AFIP mediante su portal
2. AFIP procesará tu solicitud (generalmente 24-48 horas)
3. Descarga el certificado firmado (archivo `.crt`)

---

## 💾 Paso 2: Preparar los Archivos de Certificado

### 2.1 Estructura de Directorios

```bash
# Crear directorio seguro para certificados
sudo mkdir -p /etc/lumenanalitica/afip_certs
sudo chmod 700 /etc/lumenanalitica/afip_certs

# Copiar archivos
sudo cp afip_cert.crt /etc/lumenanalitica/afip_certs/certificate.crt
sudo cp afip_private_key.pem /etc/lumenanalitica/afip_certs/private_key.pem

# Establecer permisos adecuados
sudo chmod 600 /etc/lumenanalitica/afip_certs/*
sudo chown -R www-data:www-data /etc/lumenanalitica/afip_certs  # O tu usuario de app
```

### 2.2 Verificar el Certificado

```bash
# Ver detalles del certificado
openssl x509 -in /etc/lumenanalitica/afip_certs/certificate.crt -text -noout

# Validar que la clave privada sea compatible
openssl pkey -in /etc/lumenanalitica/afip_certs/private_key.pem -text -noout
```

---

## ⚙️ Paso 3: Configurar Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# AFIP Configuration
AFIP_CUIT=20123456789
AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt
AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem
AFIP_PRODUCTION=true
```

### Permisos Necesarios

```bash
# Asegurar que la aplicación puede leer los certificados
chmod 644 /etc/lumenanalitica/afip_certs/certificate.crt
chmod 600 /etc/lumenanalitica/afip_certs/private_key.pem
```

---

## 🔧 Paso 4: Actualizar la Aplicación

### 4.1 Modificar `app.py` para usar variables de entorno

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Configuración AFIP de producción
AFIP_CUIT = os.getenv("AFIP_CUIT", "")
AFIP_CERT_PATH = os.getenv("AFIP_CERT_PATH", "")
AFIP_KEY_PATH = os.getenv("AFIP_KEY_PATH", "")
AFIP_PRODUCTION = os.getenv("AFIP_PRODUCTION", "false").lower() == "true"

# Inicializar cliente AFIP una sola vez
@st.cache_resource
def get_afip_client():
    if not AFIP_CUIT:
        st.error("AFIP_CUIT no configurado en variables de entorno")
        return None
    
    return AFIPClient(
        cuit=AFIP_CUIT,
        cert_path=AFIP_CERT_PATH if AFIP_CERT_PATH else "",
        key_path=AFIP_KEY_PATH if AFIP_KEY_PATH else "",
        production=AFIP_PRODUCTION,
        ui_feedback=True
    )

afip_client = get_afip_client()
```

### 4.2 Manejar Errores de Certificado

```python
def validate_afip_setup():
    """Valida que la configuración AFIP esté lista para producción"""
    errors = []
    
    if not AFIP_CUIT:
        errors.append("❌ AFIP_CUIT no configurado")
    
    if AFIP_PRODUCTION:
        if not AFIP_CERT_PATH or not os.path.exists(AFIP_CERT_PATH):
            errors.append(f"❌ Certificado no encontrado: {AFIP_CERT_PATH}")
        if not AFIP_KEY_PATH or not os.path.exists(AFIP_KEY_PATH):
            errors.append(f"❌ Clave privada no encontrada: {AFIP_KEY_PATH}")
    
    return errors

# Validar en inicio de la aplicación
if errors := validate_afip_setup():
    for error in errors:
        st.error(error)
    st.stop()
```

---

## 🧪 Paso 5: Pruebas

### 5.1 Ambiente de Staging (Recomendado primero)

```env
AFIP_PRODUCTION=false
AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt
AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem
```

### 5.2 Pruebas Funcionales

```python
# Script de prueba
if __name__ == "__main__":
    test_cuit = "20123456789"
    
    client = AFIPClient(
        cuit=AFIP_CUIT,
        cert_path=AFIP_CERT_PATH,
        key_path=AFIP_KEY_PATH,
        production=False  # Empezar con staging
    )
    
    result = client.get_taxpayer_details(test_cuit)
    print("✅ Conexión exitosa a AFIP!")
    print(result)
```

### 5.3 Validación de Certificado

```bash
# Verificar fecha de vencimiento
openssl x509 -in /etc/lumenanalitica/afip_certs/certificate.crt -noout -dates

# Verificar que el certificado y la clave coinciden
openssl x509 -noout -modulus -in /etc/lumenanalitica/afip_certs/certificate.crt | openssl md5
openssl rsa -noout -modulus -in /etc/lumenanalitica/afip_certs/private_key.pem | openssl md5
# Ambos deben dar el mismo hash
```

---

## 🔄 Paso 6: Implementación en Producción

### 6.1 Docker (Si usas contenedores)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copiar archivo de requisitos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación
COPY app.py .

# Crear directorio para certificados
RUN mkdir -p /etc/lumenanalitica/afip_certs

# (Los certificados se montarán como volumen en docker-compose.yml)

CMD ["streamlit", "run", "app.py", "--server.port=8501"]
```

**docker-compose.yml:**

```yaml
version: '3.8'
services:
  lumenanalitica:
    build: .
    ports:
      - "8501:8501"
    environment:
      - AFIP_CUIT=${AFIP_CUIT}
      - AFIP_PRODUCTION=true
      - AFIP_CERT_PATH=/etc/lumenanalitica/afip_certs/certificate.crt
      - AFIP_KEY_PATH=/etc/lumenanalitica/afip_certs/private_key.pem
    volumes:
      - ./afip_certs:/etc/lumenanalitica/afip_certs:ro
      - ./data:/app/data
    networks:
      - lumenanalitica-net

networks:
  lumenanalitica-net:
    driver: bridge
```

### 6.2 Ciclo de Vida del Certificado

```bash
# Listar certificados y sus fechas de vencimiento
for cert in /etc/lumenanalitica/afip_certs/*.crt; do
    echo "Certificado: $cert"
    openssl x509 -in "$cert" -noout -dates
done

# Crear alarma de renovación (cron job)
0 0 * * * python /scripts/check_cert_expiry.py
```

---

## ⚠️ Consideraciones de Seguridad

### 🔒 Seguridad de Certificados

- ✅ **Guardar clave privada con permisos 600** - Solo el propietario puede leer
- ✅ **No incluir certificados en Git** - Añadir a `.gitignore`
- ✅ **Usar variables de entorno** - No hardcodear rutas en el código
- ✅ **Hacer backup de la clave privada** - En lugar seguro (preferiblemente ofsite)
- ✅ **Rotar certificados periódicamente** - Cada 1-2 años

### 🔐 .gitignore

```
# Certificados AFIP
afip_certs/
*.crt
*.pem
*.key
*.csr

# Configuración sensible
.env
.env.local
.env.*.local
```

### 📝 Logs y Auditoría

```python
import logging

logger = logging.getLogger("afip")
logger.setLevel(logging.INFO)

# Handler para archivos
fh = logging.FileHandler("/var/log/lumenanalitica/afip.log")
fh.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

# Ejemplo de log auditado
logger.info(f"Consulta AFIP para CUIT: {cuit_ofuscado}")
```

---

## 🐛 Troubleshooting

### Error: "Certificate not found"
```
Solución: Verificar rutas en .env
sudo ls -la /etc/lumenanalitica/afip_certs/
```

### Error: "HTTP 401 - Unauthorized"
```
Solución: El certificado o clave pueden estar incorrectos
openssl verify -CAfile /path/to/ca.crt /etc/lumenanalitica/afip_certs/certificate.crt
```

### Error: "SSL: CERTIFICATE_VERIFY_FAILED"
```
Solución: Certificado vencido o fecha del sistema incorrecta
date  # Verificar hora del servidor
openssl x509 -in /etc/lumenanalitica/afip_certs/certificate.crt -noout -dates
```

### Error: "Key and certificate don't match"
```
Solución: La clave privada no corresponde al certificado
# Regenerar ambos desde cero
```

---

## 📚 Referencias

- [AFIP - Configuración de Certificados](https://www.afip.gob.ar/genericos/restservice)
- [Documentación afip.py](https://github.com/piieza/afip.py)
- [OpenSSL Manual](https://www.openssl.org/docs/)
- [Python-dotenv Documentation](https://python-dotenv.readthedocs.io/)

---

## ✅ Checklist de Implementación

- [ ] Certificado AFIP descargado de AFIP.gob.ar
- [ ] Clave privada generada localmente
- [ ] Archivos copiados a `/etc/lumenanalitica/afip_certs`
- [ ] Permisos establecidos correctamente (600/644)
- [ ] Variables de entorno configuradas en `.env`
- [ ] `python-dotenv` instalado
- [ ] Aplicación actualizada para cargar variables de entorno
- [ ] Pruebas ejecutadas en staging
- [ ] Certificado validado (no vencido)
- [ ] Logs auditados configurados
- [ ] Backup de clave privada hecho
- [ ] `.gitignore` actualizado
- [ ] Documentación de procedimiento guardada

---

**Creado:** 2026-03-31  
**Última actualización:** 2026-03-31  
**Versión:** 1.0
