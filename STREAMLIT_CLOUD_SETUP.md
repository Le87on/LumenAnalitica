# 🚀 Deploy en Streamlit Cloud - Guía Rápida

## ✅ Lo que se configuró:

1. **`.streamlit/secrets.toml`** - Configuración local (NO en Git)
2. **`.streamlit/config.toml`** - Configuración de Streamlit (tema, servidor)
3. **`app.py`** - Actualizado para leer secrets/variables de entorno

---

## 📋 Pasos para Deploy

### 1️⃣ **Commit y Push**

```bash
# Verificar cambios
git status

# Agregar archivos (secrets.toml NO se commitea)
git add .
git commit -m "Add Streamlit secrets and Cloud deployment configuration"
git push origin main
```

### 2️⃣ **En Streamlit Cloud**

Accede a: https://share.streamlit.io

**Opción A: Si es la primera vez**
```
New app → 
  Repository: Le87on/LumenAnalitica
  Branch: main
  Main file path: app.py
  → Deploy
```

**Opción B: Si ya existe la app**
- Ir a Settings → Redeployment →  "Rerun" o esperar a que se redepliegue automáticamente

### 3️⃣ **Agregar Secrets en Streamlit Cloud**

Una vez que la app esté en Streamlit Cloud:

1. Haz clic en el icono **☰ (Menú)** en la esquina superior derecha
2. Ve a **Settings** 
3. En la sección **"Secrets"**, agrega esto en formato TOML:

```toml
# AFIP Configuration
AFIP_CUIT = "20123456789"
AFIP_PRODUCTION = "true"
AFIP_CERT_PATH = "./afip_certs/certificate.crt"
AFIP_KEY_PATH = "./afip_certs/private_key.pem"
AFIP_API_TIMEOUT = 30
AFIP_MAX_RETRIES = 2

# Database
DB_PATH = "./data/creditdb.sqlite"

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "./logs/app.log"

# BCRA
BCRA_TIMEOUT = 30
```

4. Haz clic en **Save**
5. La app se redesplegará automáticamente

---

## 🔐 ¿Cómo funciona?

### En DESARROLLO (local):
```
App lee configuración:
  1. st.secrets (de `.streamlit/secrets.toml`) ← Primero
  2. os.getenv() (de `.env`) ← Luego
  3. Valor por defecto ← Si nada aplica
```

### En STREAMLIT CLOUD:
```
Streamlit Cloud lee configuración:
  1. st.secrets (del panel de Settings en web) ← Primero
  2. os.getenv() (variables del sistema) ← Luego
  3. Valor por defecto ← Si nada aplica
```

**NO necesitas cambiar nada en el código - funciona automáticamente!**

---

## 🔒 Seguridad

✅ `.streamlit/secrets.toml` está en `.gitignore` - NUNCA se commitea  
✅ `secrets.toml` es solo para desarrollo local  
✅ Streamlit Cloud tiene su propio sistema seguro de secrets  
✅ Certificados AFIP se suben SOLO a Streamlit Cloud (no en Git)

---

## 📤 Subir Certificados a Streamlit Cloud

Si quieres usar certificados REALES en producción:

### Opción A: Guardar en código (NO recomendado)
```bash
# Commit certificados a Git
git add afip_certs/
git commit -m "Add AFIP certificates"
git push
```
⚠️ **MALO**: De saldría comprometida

### Opción B: Upload manual (Recomendado)
1. En Streamlit Cloud, ve a Settings → Files
2. Upload `certificate.crt` y `private_key.pem`
3. Streamlit asignará rutas automáticas

### Opción C: Variables de entorno (MEJOR)
```toml
# En Streamlit Cloud → Settings → Secrets

AFIP_CERT = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgI...
-----END CERTIFICATE-----"""

AFIP_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"""
```

Luego en `app.py`:
```python
cert = st.secrets.get("AFIP_CERT")
key = st.secrets.get("AFIP_KEY")
client = AFIPClient(cuit, cert_content=cert, key_content=key)
```

---

## 🧪 Verificar que todo funciona

### Local:
```bash
# Asegúrate de tener .streamlit/secrets.toml
ls -la .streamlit/secrets.toml

# Prueba la app
streamlit run app.py

# Verifica en http://localhost:8501
```

### Streamlit Cloud:
1. Ve a tu app: `https://[username]-lumenanalitica.streamlit.app`
2. Ve a "Evaluación integral"
3. Ingresa un CUIT
4. Verifica que AFIP se consulte correctamente

---

## 🐛 Troubleshooting

### Error: "No certificate configured"
```
Solución:
  1. Verifica que .streamlit/secrets.toml exista localmente
  2. En Streamlit Cloud, ve a Settings → Secrets
  3. Agrega las variables AFIP_CERT_PATH, etc.
```

### Error: "Certificate not found"
```
Solución:
  1. cd /workspaces/LumenAnalitica
  2. python verify_afip_certificates.py
  3. Verifica que ./afip_certs/ exista
  4. Re-push a GitHub
```

### App se redepliegue infinitamente
```
Solución:
  1. Ve a Settings → Redeployment
  2. Marca "Ask to rerun"
  3. Haz cambios mínimos (ej: comentario) y push
  4. Reload manual
```

---

## 📊 Estado Actual

```
✅ App lista para Streamlit Cloud
✅ Secrets configurados para desarrollo
✅ Código soporta st.secrets y variables de entorno
✅ Certificados AFIP listos
✅ Sin credenciales en Git
```

---

## 📚 Referencias

- Streamlit Cloud Docs: https://share.streamlit.io
- Streamlit Secrets: https://docs.streamlit.io/streamlit-community-cloud/get-started/deploy
- Deploy Apps: https://docs.streamlit.io/deploy/streamlit-community-cloud

---

**¡Listos para ir a producción en Streamlit Cloud! 🚀**

Próximo paso: 
```bash
git push origin main
```

Luego visita Streamlit Cloud y tu app estará en línea.
