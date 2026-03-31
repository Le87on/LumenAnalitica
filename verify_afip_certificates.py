#!/usr/bin/env python3
"""
verify_afip_certificates.py - Valida y verifica certificados AFIP

Uso:
    python verify_afip_certificates.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import subprocess
from typing import Tuple, List

# Colores para terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Imprime encabezado formateado"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text:^60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")


def check_file_exists(path: str) -> Tuple[bool, str]:
    """Verifica si un archivo existe y es accesible"""
    p = Path(path)
    
    if not p.exists():
        return False, f"Archivo no encontrado: {path}"
    
    if not p.is_file():
        return False, f"No es un archivo regular: {path}"
    
    if not os.access(p, os.R_OK):
        return False, f"Archivo no legible (permisos): {path}"
    
    return True, f"✓ Archivo encontrado: {path}"


def check_certificate_validity(cert_path: str) -> Tuple[bool, List[str]]:
    """Verifica validez del certificado X.509"""
    results = []
    
    try:
        # Obtener información del certificado
        cmd = [
            "openssl", "x509",
            "-in", cert_path,
            "-text", "-noout"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return False, [f"❌ Error al procesar certificado: {result.stderr}"]
        
        cert_data = result.stdout
        
        # Extraer fechas
        cmd_dates = [
            "openssl", "x509",
            "-in", cert_path,
            "-noout", "-dates"
        ]
        
        result_dates = subprocess.run(cmd_dates, capture_output=True, text=True, timeout=10)
        dates_output = result_dates.stdout
        
        results.append(f"✓ Certificado válido (formato X.509)")
        results.append("")
        
        # Parsear fechas
        for line in dates_output.split('\n'):
            if line.strip():
                results.append(f"  {line}")
                
                # Extraer fecha de vencimiento
                if "notAfter" in line:
                    exp_date_str = line.split('=')[1]
                    # Parsear fecha en formato: Apr 15 12:34:56 2027 GMT
                    try:
                        exp_date = datetime.strptime(
                            exp_date_str.strip().replace(' GMT', ''),
                            '%b %d %H:%M:%S %Y'
                        )
                        days_left = (exp_date - datetime.now()).days
                        
                        if days_left < 0:
                            results.append(f"  {Colors.RED}❌ CERTIFICADO VENCIDO (hace {abs(days_left)} días){Colors.END}")
                            return False, results
                        elif days_left < 30:
                            results.append(f"  {Colors.YELLOW}⚠️ Certificado vence pronto ({days_left} días){Colors.END}")
                        else:
                            results.append(f"  {Colors.GREEN}✓ Certificado válido por {days_left} días{Colors.END}")
                    except:
                        pass
        
        # Extraer Subject y Issuer
        results.append("")
        cmd_subject = ["openssl", "x509", "-in", cert_path, "-noout", "-subject"]
        result_subject = subprocess.run(cmd_subject, capture_output=True, text=True, timeout=10)
        results.append(f"Subject: {result_subject.stdout.strip()}")
        
        cmd_issuer = ["openssl", "x509", "-in", cert_path, "-noout", "-issuer"]
        result_issuer = subprocess.run(cmd_issuer, capture_output=True, text=True, timeout=10)
        results.append(f"Issuer: {result_issuer.stdout.strip()}")
        
        return True, results
        
    except subprocess.TimeoutExpired:
        return False, ["❌ Timeout verificando certificado"]
    except Exception as e:
        return False, [f"❌ Error: {str(e)}"]


def check_private_key(key_path: str) -> Tuple[bool, List[str]]:
    """Verifica validez de la clave privada"""
    results = []
    
    try:
        # Verificar que es una clave RSA válida
        cmd = ["openssl", "rsa", "-in", key_path, "-text", "-noout", "-check"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return False, [f"❌ Error con clave privada: {result.stderr}"]
        
        results.append("✓ Clave privada válida (RSA)")
        
        # Extraer tamaño de clave
        if "Private-Key:" in result.stdout:
            for line in result.stdout.split('\n'):
                if "Private-Key:" in line:
                    results.append(f"  {line.strip()}")
        
        return True, results
        
    except subprocess.TimeoutExpired:
        return False, ["❌ Timeout verificando clave privada"]
    except Exception as e:
        return False, [f"❌ Error: {str(e)}"]


def check_cert_key_match(cert_path: str, key_path: str) -> Tuple[bool, str]:
    """Verifica que certificado y clave privada coincidan"""
    
    try:
        # Obtener hash del modulus del certificado
        cmd_cert = ["openssl", "x509", "-noout", "-modulus", "-in", cert_path]
        result_cert = subprocess.run(cmd_cert, capture_output=True, text=True, timeout=10)
        
        if result_cert.returncode != 0:
            return False, "Error obteniendo modulus del certificado"
        
        cert_modulus = result_cert.stdout.strip()
        
        # Obtener hash del modulus de la clave privada
        cmd_key = ["openssl", "rsa", "-noout", "-modulus", "-in", key_path]
        result_key = subprocess.run(cmd_key, capture_output=True, text=True, timeout=10)
        
        if result_key.returncode != 0:
            return False, "Error obteniendo modulus de la clave privada"
        
        key_modulus = result_key.stdout.strip()
        
        # Comparar
        if cert_modulus == key_modulus:
            return True, "✓ Certificado y clave privada coinciden"
        else:
            return False, "❌ Certificado y clave privada NO coinciden"
            
    except Exception as e:
        return False, f"❌ Error comparando: {str(e)}"


def check_file_permissions(path: str) -> Tuple[str, str]:
    """Verifica permisos del archivo"""
    p = Path(path)
    
    if not p.exists():
        return "N/A", "Archivo no existe"
    
    mode = oct(p.stat().st_mode)[-3:]
    owner = p.owner()
    
    return mode, f"Propietario: {owner}"


def main():
    """Función principal"""
    
    print_header("Verificador de Certificados AFIP")
    
    # Cargar configuración
    from dotenv import load_dotenv
    load_dotenv()
    
    cert_path = os.getenv("AFIP_CERT_PATH", "").strip()
    key_path = os.getenv("AFIP_KEY_PATH", "").strip()
    cuit = os.getenv("AFIP_CUIT", "").strip()
    production = os.getenv("AFIP_PRODUCTION", "false").lower() == "true"
    
    print(f"Configuración cargada desde: {Path('.env').absolute()}")
    print(f"  CUIT: {cuit[:2] + '***' + cuit[-3:] if cuit else 'NO CONFIGURADO'}")
    print(f"  Modo producción: {'SÍ' if production else 'NO'}")
    print(f"  Certificado: {cert_path if cert_path else 'NO CONFIGURADO'}")
    print(f"  Clave privada: {key_path if key_path else 'NO CONFIGURADA'}")
    
    # Validar CUIT
    print(f"\n{Colors.BOLD}1. Validación de CUIT{Colors.END}")
    print("-" * 60)
    if not cuit:
        print(f"{Colors.RED}❌ AFIP_CUIT no configurado{Colors.END}")
        return 1
    elif len(cuit.replace("-", "").replace(" ", "")) != 11:
        print(f"{Colors.RED}❌ AFIP_CUIT inválido: {cuit} (debe ser 11 dígitos){Colors.END}")
        return 1
    else:
        print(f"{Colors.GREEN}✓ CUIT válido: {cuit}{Colors.END}")
    
    # Validar certificado
    print(f"\n{Colors.BOLD}2. Validación de Certificado{Colors.END}")
    print("-" * 60)
    
    if not cert_path:
        print(f"{Colors.YELLOW}⚠️ AFIP_CERT_PATH no configurado{Colors.END}")
    else:
        exists, msg = check_file_exists(cert_path)
        if exists:
            print(f"{Colors.GREEN}{msg}{Colors.END}")
            perms, owner = check_file_permissions(cert_path)
            print(f"  Permisos: {perms} ({owner})")
            
            valid, details = check_certificate_validity(cert_path)
            for line in details:
                print(f"  {line}")
        else:
            print(f"{Colors.RED}❌ {msg}{Colors.END}")
            return 1
    
    # Validar clave privada
    print(f"\n{Colors.BOLD}3. Validación de Clave Privada{Colors.END}")
    print("-" * 60)
    
    if not key_path:
        print(f"{Colors.YELLOW}⚠️ AFIP_KEY_PATH no configurado{Colors.END}")
    else:
        exists, msg = check_file_exists(key_path)
        if exists:
            print(f"{Colors.GREEN}{msg}{Colors.END}")
            perms, owner = check_file_permissions(key_path)
            print(f"  Permisos: {perms} ({owner})")
            
            valid, details = check_private_key(key_path)
            for line in details:
                print(f"  {line}")
        else:
            print(f"{Colors.RED}❌ {msg}{Colors.END}")
            return 1
    
    # Validar compatibilidad
    if cert_path and key_path:
        print(f"\n{Colors.BOLD}4. Validación de Compatibilidad{Colors.END}")
        print("-" * 60)
        
        if check_file_exists(cert_path)[0] and check_file_exists(key_path)[0]:
            match, msg = check_cert_key_match(cert_path, key_path)
            if match:
                print(f"{Colors.GREEN}{msg}{Colors.END}")
            else:
                print(f"{Colors.RED}{msg}{Colors.END}")
                return 1
    
    # Resumen
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}✓ Todos los certificados están correctamente configurados{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'=' * 60}{Colors.END}\n")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Operación cancelada por el usuario{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Error inesperado: {str(e)}{Colors.END}")
        sys.exit(1)
