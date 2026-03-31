"""
config.py - Configuración de AFIP y variables de entorno para producción
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# ============================================================
# CONFIGURACIÓN AFIP
# ============================================================

class AFIPConfig:
    """Configuración centralizada para AFIP"""
    
    # Credenciales
    CUIT = os.getenv("AFIP_CUIT", "").strip()
    
    # Rutas de certificados
    CERT_PATH = os.getenv("AFIP_CERT_PATH", "").strip()
    KEY_PATH = os.getenv("AFIP_KEY_PATH", "").strip()
    
    # Modo producción
    PRODUCTION = os.getenv("AFIP_PRODUCTION", "false").lower() == "true"
    
    # Timeout para consultas
    API_TIMEOUT = int(os.getenv("AFIP_API_TIMEOUT", "30"))
    
    # Reintentos en caso de error
    MAX_RETRIES = int(os.getenv("AFIP_MAX_RETRIES", "2"))
    
    @classmethod
    def validate(cls) -> list[str]:
        """
        Valida que la configuración AFIP sea correcta.
        Retorna lista de errores (vacía si todo está bien).
        """
        errors = []
        
        # Validar CUIT
        if not cls.CUIT:
            errors.append("❌ AFIP_CUIT no configurado en variables de entorno")
        elif len(cls.CUIT.replace("-", "").replace(" ", "")) != 11:
            errors.append(f"❌ AFIP_CUIT inválido: '{cls.CUIT}' (debe ser 11 dígitos)")
        
        # Validar certificados si es producción
        if cls.PRODUCTION:
            if not cls.CERT_PATH:
                errors.append("❌ AFIP_CERT_PATH no configurado (requerido en producción)")
            elif not Path(cls.CERT_PATH).exists():
                errors.append(f"❌ Certificado AFIP no encontrado: {cls.CERT_PATH}")
            
            if not cls.KEY_PATH:
                errors.append("❌ AFIP_KEY_PATH no configurado (requerido en producción)")
            elif not Path(cls.KEY_PATH).exists():
                errors.append(f"❌ Clave privada AFIP no encontrada: {cls.KEY_PATH}")
        else:
            # En staging, certificados son opcionales pero se avisa
            if cls.CERT_PATH and not Path(cls.CERT_PATH).exists():
                errors.append(f"⚠️ Certificado AFIP no encontrado (staging): {cls.CERT_PATH}")
        
        return errors
    
    @classmethod
    def is_ready(cls) -> bool:
        """Retorna True si la configuración es válida"""
        return len(cls.validate()) == 0
    
    @classmethod
    def get_status(cls) -> dict:
        """Retorna estado de la configuración"""
        return {
            "cuit": cls.CUIT[:2] + "***" + cls.CUIT[-3:] if cls.CUIT else "No configurado",
            "production": cls.PRODUCTION,
            "cert_configured": bool(cls.CERT_PATH and Path(cls.CERT_PATH).exists()),
            "key_configured": bool(cls.KEY_PATH and Path(cls.KEY_PATH).exists()),
            "ready": cls.is_ready(),
        }


# ============================================================
# CONFIGURACIÓN GENERALE DE APLICACIÓN
# ============================================================

class AppConfig:
    """Configuración general de la aplicación"""
    
    # Base de datos
    DB_PATH = os.getenv("DB_PATH", "/app/data/creditdb.sqlite")
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "/var/log/lumenanalitica/app.log")
    
    # BCRA
    BCRA_API_URL = "https://www.bcra.gob.ar/api"
    BCRA_TIMEOUT = int(os.getenv("BCRA_TIMEOUT", "30"))
    
    # Streamlit
    STREAMLIT_SECRET_KEY = os.getenv("STREAMLIT_SECRET_KEY", "dev-secret-key-change-in-production")


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def setup_logging():
    """Configura logging para la aplicación"""
    import logging
    
    log_dir = Path(AppConfig.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=AppConfig.LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(AppConfig.LOG_FILE),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger("lumenanalitica")
    return logger


def check_environment():
    """Chequea y reporta estado del ambiente"""
    import streamlit as st
    
    errors = AFIPConfig.validate()
    
    if errors:
        st.error("⚠️ **Problemas de configuración detectados:**")
        for error in errors:
            st.error(error)
        
        if AFIPConfig.PRODUCTION:
            st.stop()
        else:
            st.warning("⚠️ Modo staging detectado. Algunos servicios pueden no funcionar completamente.")
    
    return len(errors) == 0


if __name__ == "__main__":
    # Mostrar estado de configuración
    print("\n📋 Estado de Configuración AFIP")
    print("=" * 50)
    
    status = AFIPConfig.get_status()
    for key, value in status.items():
        print(f"{key.upper():<20} : {value}")
    
    print("\n⚠️ Validación de Configuración")
    print("=" * 50)
    errors = AFIPConfig.validate()
    
    if not errors:
        print("✅ Configuración AFIP válida")
    else:
        for error in errors:
            print(error)
