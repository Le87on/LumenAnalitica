#!/usr/bin/env python3
"""
setup_afip_dev.py - Setup automático de certificados AFIP para desarrollo

Este script genera certificados autofirmados para pruebas en desarrollo.
NUNCA usar estos certificados en producción.

Uso:
    python setup_afip_dev.py --cuit 20123456789
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_step(step: int, title: str):
    """Imprime paso del proceso"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}Paso {step}: {title}{Colors.END}")
    print("-" * 60)


def run_command(cmd: list, description: str = "") -> bool:
    """Ejecuta comando y reporta resultado"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"{Colors.RED}❌ Error{Colors.END}: {description}")
            if result.stderr:
                print(f"   {result.stderr}")
            return False
        print(f"{Colors.GREEN}✓ {description}{Colors.END}")
        return True
    except Exception as e:
        print(f"{Colors.RED}❌ Excepción: {e}{Colors.END}")
        return False


def setup_dev_certificates(cuit: str, output_dir: str = "./afip_certs") -> bool:
    """Configura certificados autofirmados para desarrollo"""
    
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}Generador de Certificados AFIP para Desarrollo{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"\n{Colors.YELLOW}⚠️  ADVERTENCIA: Estos certificados son SOLO para desarrollo{Colors.END}")
    print(f"{Colors.YELLOW}    NO usar en producción{Colors.END}")
    
    # Crear directorio
    print_step(1, "Crear directorio de certificados")
    cert_path = Path(output_dir)
    cert_path.mkdir(parents=True, exist_ok=True)
    print(f"{Colors.GREEN}✓ Directorio: {cert_path.absolute()}{Colors.END}")
    
    # Generar clave privada
    print_step(2, "Generar clave privada RSA (2048 bits)")
    key_file = cert_path / "private_key.pem"
    if not run_command(
        ["openssl", "genrsa", "-out", str(key_file), "2048"],
        "Clave privada generada"
    ):
        return False
    
    # Generar Certificate Signing Request (CSR)
    print_step(3, "Generar Certificate Signing Request (CSR)")
    csr_file = cert_path / "certificate.csr"
    subject = f"/C=AR/ST=Buenos Aires/L=Buenos Aires/O=Test Company/CN={cuit}"
    if not run_command(
        ["openssl", "req", "-new",
         "-key", str(key_file),
         "-out", str(csr_file),
         "-subj", subject],
        "CSR generado"
    ):
        return False
    
    # Generar certificado autofirmado (válido por 365 días)
    print_step(4, "Generar certificado autofirmado X.509")
    cert_file = cert_path / "certificate.crt"
    if not run_command(
        ["openssl", "x509", "-req",
         "-days", "365",
         "-in", str(csr_file),
         "-signkey", str(key_file),
         "-out", str(cert_file)],
        "Certificado autofirmado generado (válido por 365 días)"
    ):
        return False
    
    # Establecer permisos
    print_step(5, "Establecer permisos de archivos")
    os.chmod(key_file, 0o600)  # Solo propietario puede leer
    os.chmod(cert_file, 0o644)  # Puede ser leído por todos
    print(f"{Colors.GREEN}✓ Permisos establecidos (key: 600, cert: 644){Colors.END}")
    
    # Mostrar información de certificado
    print_step(6, "Información del certificado")
    print_command = ["openssl", "x509", "-in", str(cert_file), "-text", "-noout"]
    try:
        result = subprocess.run(print_command, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            # Mostrar solo líneas importantes
            for line in result.stdout.split('\n'):
                if any(x in line for x in ['Subject:', 'Issuer:', 'Not Before', 'Not After', 'CN=']):
                    print(f"  {line.strip()}")
    except:
        pass
    
    # Crear/actualizar .env
    print_step(7, "Actualizar archivo .env")
    env_file = Path(".env")
    env_content = f"""# AFIP Configuration (Desarrollo)
AFIP_CUIT={cuit}
AFIP_CERT_PATH={cert_path.absolute()}/certificate.crt
AFIP_KEY_PATH={cert_path.absolute()}/private_key.pem
AFIP_PRODUCTION=false
AFIP_API_TIMEOUT=30
AFIP_MAX_RETRIES=2
DB_PATH=./data/creditdb.sqlite
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log
BCRA_TIMEOUT=30
"""
    
    # Si .env existe, hacer backup
    if env_file.exists():
        backup_file = env_file.with_stem(".env.backup")
        env_file.rename(backup_file)
        print(f"{Colors.YELLOW}⚠️  Archivo .env existente renombrado a .env.backup{Colors.END}")
    
    env_file.write_text(env_content)
    print(f"{Colors.GREEN}✓ Archivo .env creado/actualizado{Colors.END}")
    
    # Resumen final
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}✓ Setup completado exitosamente{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'=' * 60}{Colors.END}")
    
    print(f"\n{Colors.BOLD}Próximos pasos:{Colors.END}")
    print(f"  1. Instalar dependencias: {Colors.BLUE}pip install -r requirements.txt{Colors.END}")
    print(f"  2. Verificar certificados: {Colors.BLUE}python verify_afip_certificates.py{Colors.END}")
    print(f"  3. Iniciar aplicación: {Colors.BLUE}streamlit run app.py{Colors.END}")
    
    print(f"\n{Colors.YELLOW}Recuerda:{Colors.END}")
    print(f"  • Certificados guardados en: {Colors.BOLD}{cert_path.absolute()}{Colors.END}")
    print(f"  • Configuración en: {Colors.BOLD}.env{Colors.END}")
    print(f"  • NO usar estos certificados en producción")
    print(f"  • Para producción, obtener certificados reales de AFIP.gob.ar")
    
    return True


def main():
    """Función principal"""
    
    parser = argparse.ArgumentParser(
        description="Configurar certificados AFIP para desarrollo"
    )
    parser.add_argument(
        "--cuit",
        type=str,
        default="20123456789",
        help="CUIT a usar en certificados (default: 20123456789)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./afip_certs",
        help="Directorio donde guardar certificados (default: ./afip_certs)"
    )
    
    args = parser.parse_args()
    
    # Validar CUIT
    cuit = args.cuit.replace("-", "").replace(" ", "")
    if len(cuit) != 11 or not cuit.isdigit():
        print(f"{Colors.RED}❌ CUIT inválido: {args.cuit}{Colors.END}")
        print(f"   El CUIT debe tener 11 dígitos")
        return 1
    
    # Validar que openssl esté disponible
    try:
        subprocess.run(["openssl", "version"], capture_output=True, timeout=5)
    except FileNotFoundError:
        print(f"{Colors.RED}❌ OpenSSL no está instalado{Colors.END}")
        print(f"   Instálalo con: sudo apt-get install openssl (Linux/Mac)")
        return 1
    
    # Ejecutar setup
    if setup_dev_certificates(cuit, args.output_dir):
        return 0
    else:
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Operación cancelada por el usuario{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Error inesperado: {str(e)}{Colors.END}")
        sys.exit(1)
