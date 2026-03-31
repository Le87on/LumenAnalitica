from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
from afip import Afip
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# ============================================================
# CONFIG
# ============================================================
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "credit_app.db"
BCRA_BASE_URL = "https://api.bcra.gob.ar"
TIMEOUT = 15

# Load environment variables
load_dotenv(APP_DIR / ".env")

# ============================================================
# CONFIGURACIÓN STREAMLIT SECRETS / ENVIRONMENT
# ============================================================
def get_config(key: str, default: Any = None) -> Any:
    """
    Obtiene configuración desde:
    1. Streamlit Secrets (en Streamlit Cloud)
    2. Variables de entorno (en desarrollo)
    3. Valor por defecto
    """
    try:
        # Primero intenta desde st.secrets (Streamlit Cloud)
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except:
        pass
    
    # Luego desde variables de entorno
    env_value = os.getenv(key)
    if env_value is not None:
        # Convertir a bool si es necesario
        if env_value.lower() in ("true", "false"):
            return env_value.lower() == "true"
        # Convertir a int si es numero
        if env_value.isdigit():
            return int(env_value)
        return env_value
    
    return default

# AFIP Configuration
AFIP_CUIT = get_config("AFIP_CUIT", "")
AFIP_CERT_PATH = get_config("AFIP_CERT_PATH", str(APP_DIR / "afip_certs" / "certificate.crt"))
AFIP_KEY_PATH = get_config("AFIP_KEY_PATH", str(APP_DIR / "afip_certs" / "private_key.pem"))
AFIP_PRODUCTION = get_config("AFIP_PRODUCTION", False)
AFIP_API_TIMEOUT = get_config("AFIP_API_TIMEOUT", 30)
AFIP_MAX_RETRIES = get_config("AFIP_MAX_RETRIES", 2)

Segmento = Literal["persona", "empresa"]
Decision = Literal["APROBAR", "REVISAR", "RECHAZAR"]


# ============================================================
# MODELOS
# ============================================================
@dataclass
class ClienteInput:
    nombre: str
    documento: str
    segmento: Segmento
    patrimonio_estimado: float = 0.0
    liquidez_inmediata: float = 0.0
    sueldo_neto: float = 0.0
    ingreso_mensual: float = 0.0
    ventas_mensuales: float = 0.0
    egresos_mensuales: float = 0.0
    cuota_propuesta: float = 0.0
    cuotas_existentes: float = 0.0
    observaciones: str = ""


@dataclass
class BCRAResumen:
    identificacion: str
    denominacion: str
    periodo: str = ""
    deuda_total_miles: float = 0.0
    deuda_total_pesos: float = 0.0
    peor_situacion: int = 0
    dias_atraso_max: int = 0
    entidades: List[Dict[str, Any]] = field(default_factory=list)
    refinanciaciones: bool = False
    recategorizacion_oblig: bool = False
    situacion_juridica: bool = False
    irrec_disposicion_tecnica: bool = False
    en_revision: bool = False
    proceso_jud: bool = False


@dataclass
class ChequesRechazadosResumen:
    cantidad_total: int = 0
    monto_total: float = 0.0
    causales: List[Dict[str, Any]] = field(default_factory=list)
    multa_impaga: bool = False


@dataclass
class AFIPResumen:
    identificacion: str
    nombre: str = ""
    tipo_persona: str = ""
    estado: str = ""
    domicilio: str = ""
    actividades: List[Dict[str, Any]] = field(default_factory=list)
    impuestos: List[Dict[str, Any]] = field(default_factory=list)
    al_dia: bool = True  # Asumir al día si no hay deudas conocidas


@dataclass
class ChequeDenunciadoResultado:
    numero_cheque: int
    denunciado: bool
    fecha_procesamiento: str = ""
    denominacion_entidad: str = ""
    detalles: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ResultadoEvaluacion:
    score_total: float
    decision: Decision
    score_credito: float
    score_cheques: float
    score_patrimonial: float
    score_afip: float
    motivos: List[str] = field(default_factory=list)
    resumen_llm_style: str = ""


# ============================================================
# DB
# ============================================================
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
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
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_users_table() -> None:
    conn = get_conn()
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL
        )
        """)
        existing = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if existing == 0:
            conn.execute(
                "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)",
                ("admin", hash_password("admin123"), "admin"),
            )
            conn.commit()
    finally:
        conn.close()


def authenticate_user(username: str, password: str):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT username, rol FROM usuarios WHERE username = ? AND password_hash = ?",
            (username, hash_password(password)),
        ).fetchone()
        if row:
            return {"username": row[0], "rol": row[1]}
        return None
    finally:
        conn.close()

def save_eval(
    cliente: ClienteInput,
    bcra: Optional[BCRAResumen],
    cheques: Optional[ChequesRechazadosResumen],
    afip: Optional[AFIPResumen],
    resultado: ResultadoEvaluacion,
) -> None:
    payload = {
        "cliente": asdict(cliente),
        "bcra": asdict(bcra) if bcra else {},
        "cheques": asdict(cheques) if cheques else {},
        "afip": asdict(afip) if afip else {},
        "resultado": asdict(resultado),
    }
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO evaluaciones (
                fecha, nombre, documento, segmento, score_total, decision,
                score_credito, score_cheques, score_patrimonial,
                deuda_total_pesos, peor_situacion, cheques_rechazados,
                patrimonio_estimado, liquidez_inmediata, observaciones, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                cliente.nombre,
                cliente.documento,
                cliente.segmento,
                resultado.score_total,
                resultado.decision,
                resultado.score_credito,
                resultado.score_cheques,
                resultado.score_patrimonial,
                bcra.deuda_total_pesos if bcra else 0.0,
                bcra.peor_situacion if bcra else 0,
                cheques.cantidad_total if cheques else 0,
                cliente.patrimonio_estimado,
                cliente.liquidez_inmediata,
                cliente.observaciones,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def load_history(search_doc: str = "") -> pd.DataFrame:
    conn = get_conn()
    try:
        if search_doc.strip():
            return pd.read_sql_query(
                "SELECT * FROM evaluaciones WHERE documento LIKE ? ORDER BY id DESC",
                conn,
                params=(f"%{search_doc.strip()}%",),
            )
        return pd.read_sql_query("SELECT * FROM evaluaciones ORDER BY id DESC", conn)
    finally:
        conn.close()


# ============================================================
# UTILIDADES
# ============================================================
def clean_doc(doc: str) -> str:
    return re.sub(r"\D", "", doc or "")


def validar_identificacion(doc: str) -> bool:
    return len(clean_doc(doc)) == 11


def situacion_label(situacion: int) -> str:
    return {
        1: "Situación 1: Normal",
        2: "Situación 2: Riesgo bajo / seguimiento especial",
        3: "Situación 3: Con problemas / riesgo medio",
        4: "Situación 4: Alto riesgo",
        5: "Situación 5: Irrecuperable",
    }.get(int(situacion or 0), "Situación no informada")


def metric_card(label: str, value: str) -> None:
    st.markdown(
        f"""
        <div style='padding:14px;border:1px solid #2d3748;border-radius:14px;background:#111827;'>
            <div style='font-size:0.88rem;color:#9ca3af'>{label}</div>
            <div style='font-size:1.5rem;font-weight:700'>{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dataframe_download_button(df: pd.DataFrame, label: str, filename: str) -> None:
    """Genera un botón para descargar un DataFrame como PDF."""
    pdf_buffer = io.BytesIO()
    pdf = canvas.Canvas(pdf_buffer, pagesize=A4)
    width, height = A4
    margin = 0.5 * cm
    y_pos = height - margin
    
    # Título
    pdf.setFont("Helvetica-Bold", 12)
    title = filename.replace(".pdf", "").replace("_", " ").title()
    pdf.drawString(margin, y_pos, title)
    y_pos -= 0.5 * cm
    
    # Tabla
    pdf.setFont("Helvetica", 9)
    col_widths = [width / len(df.columns) - 0.2 * cm for _ in df.columns]
    row_height = 0.4 * cm
    
    # Encabezados
    x_pos = margin
    for col, col_width in zip(df.columns, col_widths):
        pdf.drawString(x_pos + 0.1 * cm, y_pos, str(col)[:20])
        x_pos += col_width
    y_pos -= row_height
    
    # Datos
    for _, row in df.iterrows():
        if y_pos < margin:
            pdf.showPage()
            y_pos = height - margin
            pdf.setFont("Helvetica", 9)
        
        x_pos = margin
        for cell, col_width in zip(row, col_widths):
            cell_str = str(cell)[:20]
            pdf.drawString(x_pos + 0.1 * cm, y_pos, cell_str)
            x_pos += col_width
        y_pos -= row_height
    
    pdf.save()
    pdf_buffer.seek(0)
    
    st.download_button(
        label,
        data=pdf_buffer.getvalue(),
        file_name=filename.replace(".csv", ".pdf"),
        mime="application/pdf",
        use_container_width=True,
    )


def _wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if stringWidth(trial, font_name, font_size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def build_pdf_report(
    cliente: ClienteInput,
    bcra: Optional[BCRAResumen],
    cheques: Optional[ChequesRechazadosResumen],
    resultado: ResultadoEvaluacion,
) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin = 2 * cm
    y = height - margin

    def new_page() -> None:
        nonlocal y
        pdf.showPage()
        y = height - margin

    def line(text: str, size: int = 10, bold: bool = False) -> None:
        nonlocal y
        font = "Helvetica-Bold" if bold else "Helvetica"
        pdf.setFont(font, size)
        wrapped = _wrap_text(text, font, size, width - (2 * margin))
        needed = len(wrapped) * (size + 3) + 8
        if y - needed < margin:
            new_page()
            pdf.setFont(font, size)
        for ln in wrapped:
            pdf.drawString(margin, y, ln)
            y -= size + 3
        y -= 2

    pdf.setTitle(f"Informe de crédito - {cliente.documento}")
    line("INFORME DE CRÉDITO BANCARIO", size=16, bold=True)
    line(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    line("")

    line("1. Datos del cliente", size=12, bold=True)
    line(f"Nombre / Razón social: {cliente.nombre}")
    line(f"Documento: {cliente.documento}")
    line(f"Segmento: {cliente.segmento}")
    line(f"Patrimonio estimado: ${cliente.patrimonio_estimado:,.2f}")
    line(f"Liquidez inmediata: ${cliente.liquidez_inmediata:,.2f}")
    if cliente.segmento == "persona":
        line(f"Sueldo neto: ${cliente.sueldo_neto:,.2f}")
        line(f"Ingreso mensual total: ${cliente.ingreso_mensual:,.2f}")
    else:
        line(f"Ventas mensuales: ${cliente.ventas_mensuales:,.2f}")
        line(f"Egresos mensuales: ${cliente.egresos_mensuales:,.2f}")
    line(f"Cuotas existentes: ${cliente.cuotas_existentes:,.2f}")
    if cliente.observaciones:
        line(f"Observaciones del analista: {cliente.observaciones}")

    line("2. Central de Deudores", size=12, bold=True)
    if bcra:
        line(f"Denominación BCRA: {bcra.denominacion or '-'}")
        line(f"Período informado: {bcra.periodo or '-'}")
        line(f"Peor situación: {situacion_label(bcra.peor_situacion)}")
        line(f"Deuda consolidada estimada: ${bcra.deuda_total_pesos:,.2f}")
        line(f"Máximo días de atraso: {bcra.dias_atraso_max}")
        flags: List[str] = []
        if bcra.refinanciaciones:
            flags.append("Refinanciaciones")
        if bcra.recategorizacion_oblig:
            flags.append("Recategorización obligatoria")
        if bcra.situacion_juridica:
            flags.append("Situación jurídica")
        if bcra.irrec_disposicion_tecnica:
            flags.append("Irrecuperable por disposición técnica")
        if bcra.en_revision:
            flags.append("En revisión")
        if bcra.proceso_jud:
            flags.append("Proceso judicial")
        line(f"Flags detectadas: {', '.join(flags) if flags else 'Sin flags relevantes'}")
    else:
        line("No se pudo obtener información de Central de Deudores.")

    line("3. Cheques", size=12, bold=True)
    if cheques:
        line(f"Cantidad total de cheques rechazados: {cheques.cantidad_total}")
        line(f"Monto total rechazado: ${cheques.monto_total:,.2f}")
        line(f"Multa impaga detectada: {'Sí' if cheques.multa_impaga else 'No'}")
    else:
        line("No se pudo obtener información de cheques rechazados.")

    line("4. Resultado del análisis", size=12, bold=True)
    line(f"Score crédito: {resultado.score_credito:.2f}")
    line(f"Score cheques: {resultado.score_cheques:.2f}")
    line(f"Score patrimonial: {resultado.score_patrimonial:.2f}")
    line(f"Score total: {resultado.score_total:.2f}", bold=True)
    line(f"Decisión sugerida: {resultado.decision}", bold=True)

    line("5. Dictamen del sistema", size=12, bold=True)
    line(resultado.resumen_llm_style or "Sin dictamen generado.")

    line("6. Alertas relevantes", size=12, bold=True)
    if resultado.motivos:
        for idx, motivo in enumerate(resultado.motivos, start=1):
            line(f"{idx}. {motivo}")
    else:
        line("Sin alertas relevantes.")

    line("")
    line("Firma del analista: ________________________________", size=11)
    line("Aclaración: ______________________________________", size=11)

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# CLIENTE BCRA
# ============================================================
class BCRAClient:
    _memory_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
    _cache_lock = threading.Lock()

    def __init__(self, timeout: int = TIMEOUT, ui_feedback: bool = True) -> None:
        self.timeout = timeout
        self.ui_feedback = ui_feedback
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CreditWorkbench/1.1",
                "Accept": "application/json",
            }
        )

    def _notify(self, msg: str, level: str = "warning") -> None:
        if self.ui_feedback:
            fn = getattr(st, level, None)
            if callable(fn):
                fn(msg)

    def _get(self, path: str, cache_ttl_min: int = 10) -> Dict[str, Any]:
        url = f"{BCRA_BASE_URL.rstrip('/')}/{path.lstrip('/')}"

        with self._cache_lock:
            if url in self._memory_cache:
                data, timestamp = self._memory_cache[url]
                if datetime.now() < timestamp + timedelta(minutes=cache_ttl_min):
                    return data

        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=self.timeout)

                if response.status_code == 200:
                    raw_data = response.json()
                    result = raw_data.get("results", {})
                    with self._cache_lock:
                        self._memory_cache[url] = (result, datetime.now())
                    return result

                if response.status_code == 404:
                    with self._cache_lock:
                        self._memory_cache[url] = ({}, datetime.now())
                    return {}

                if response.status_code == 429:
                    wait = (2 ** attempt) + 1
                    self._notify(f"BCRA saturado. Reintentando en {wait}s...", "warning")
                    time.sleep(wait)
                    continue

                self._notify(
                    f"BCRA error {response.status_code}: {response.reason}",
                    "error",
                )
                break

            except (requests.Timeout, requests.ConnectionError):
                if attempt == 2:
                    self._notify("No se pudo conectar con el BCRA tras 3 intentos.", "error")
                time.sleep(1.5)

            except requests.RequestException as exc:
                self._notify(f"Error de red BCRA: {exc}", "error")
                break

            except Exception as exc:
                self._notify(f"Error inesperado: {exc}", "error")
                break

        return {}

    def get_deudas(self, identificacion: str) -> Dict[str, Any]:
        return self._get(f"/CentralDeDeudores/v1.0/Deudas/{clean_doc(identificacion)}")

    def get_historicas(self, identificacion: str) -> Dict[str, Any]:
        return self._get(f"/CentralDeDeudores/v1.0/Deudas/Historicas/{clean_doc(identificacion)}")

    def get_cheques_rechazados(self, identificacion: str) -> Dict[str, Any]:
        return self._get(f"/CentralDeDeudores/v1.0/Deudas/ChequesRechazados/{clean_doc(identificacion)}")

    def get_entidades(self) -> List[Dict[str, Any]]:
        return self._get("/cheques/v1.0/entidades", cache_ttl_min=60)

    def get_cheque_denunciado(self, codigo_entidad: int, numero_cheque: int) -> Dict[str, Any]:
        return self._get(f"/cheques/v1.0/denunciados/{codigo_entidad}/{numero_cheque}", cache_ttl_min=10)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def bcra_get_deudas(identificacion: str) -> Dict[str, Any]:
    return BCRAClient(ui_feedback=False).get_deudas(identificacion)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def bcra_get_historicas(identificacion: str) -> Dict[str, Any]:
    return BCRAClient(ui_feedback=False).get_historicas(identificacion)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def bcra_get_cheques_rechazados(identificacion: str) -> Dict[str, Any]:
    return BCRAClient(ui_feedback=False).get_cheques_rechazados(identificacion)


@st.cache_data(show_spinner=False, ttl=60 * 60 * 12)
def bcra_get_entidades() -> List[Dict[str, Any]]:
    return BCRAClient(ui_feedback=False).get_entidades()


@st.cache_data(show_spinner=False, ttl=60 * 10)
def bcra_get_cheque_denunciado(codigo_entidad: int, numero_cheque: int) -> Dict[str, Any]:
    return BCRAClient(ui_feedback=False).get_cheque_denunciado(codigo_entidad, numero_cheque)


# ============================================================
# CLIENTE AFIP
# ============================================================
class AFIPClient:
    def __init__(self, cuit: str, cert_path: str = "", key_path: str = "", production: bool = False, ui_feedback: bool = True) -> None:
        self.ui_feedback = ui_feedback
        options = {
            "CUIT": cuit,
            "production": production,
        }
        if cert_path and key_path:
            with open(cert_path, 'r') as f:
                options["cert"] = f.read()
            with open(key_path, 'r') as f:
                options["key"] = f.read()
        self.afip = Afip(options)

    def _notify(self, msg: str, level: str = "info") -> None:
        if self.ui_feedback:
            fn = getattr(st, level, None)
            if callable(fn):
                fn(msg)

    def get_taxpayer_details(self, identifier: str) -> Dict[str, Any]:
        try:
            return self.afip.RegisterInscriptionProof.getTaxpayerDetails(identifier)
        except Exception as e:
            self._notify(f"Error obteniendo datos del contribuyente AFIP: {e}", "error")
            return {}

    def get_taxpayer_voucher_info(self, sales_point: int, voucher_type: int, voucher_number: int) -> Dict[str, Any]:
        try:
            return self.afip.ElectronicBilling.getVoucherInfo(voucher_number, sales_point, voucher_type)
        except Exception as e:
            self._notify(f"Error obteniendo info de comprobante AFIP: {e}", "error")
            return {}


@st.cache_data(show_spinner=False, ttl=60 * 60)
def afip_get_taxpayer_details(cuit: str, identifier: str) -> Dict[str, Any]:
    """Obtiene detalles del contribuyente desde AFIP usando certificados configurados"""
    client = AFIPClient(
        cuit=AFIP_CUIT,
        cert_path=AFIP_CERT_PATH,
        key_path=AFIP_KEY_PATH,
        production=AFIP_PRODUCTION,
        ui_feedback=False
    )
    return client.get_taxpayer_details(identifier)


def parse_afip_resumen(raw: Dict[str, Any]) -> AFIPResumen:
    return AFIPResumen(
        identificacion=raw.get("idPersona", ""),
        nombre=raw.get("persona", {}).get("nombre", "") + " " + raw.get("persona", {}).get("apellido", ""),
        tipo_persona=raw.get("persona", {}).get("tipoPersona", ""),
        estado=raw.get("persona", {}).get("estadoClave", ""),
        domicilio=raw.get("persona", {}).get("domicilioFiscal", {}).get("direccion", ""),
        actividades=raw.get("persona", {}).get("actividades", {}).get("actividad", []) if raw.get("persona", {}).get("actividades") else [],
        impuestos=raw.get("persona", {}).get("impuestos", {}).get("impuesto", []) if raw.get("persona", {}).get("impuestos") else [],
        al_dia=not any(imp.get("estado", "") == "DEUDA" for imp in (raw.get("persona", {}).get("impuestos", {}).get("impuesto", []) if raw.get("persona", {}).get("impuestos") else []))
    )


# ============================================================
# NORMALIZADORES
# ============================================================
def parse_bcra_resumen(raw: Dict[str, Any]) -> BCRAResumen:
    periodos = raw.get("periodos", []) or []
    ultimo = periodos[0] if periodos else {}
    entidades = ultimo.get("entidades", []) or []

    deuda_miles = sum(float(e.get("monto", 0) or 0) for e in entidades)
    peor_situacion = max((int(e.get("situacion", 0) or 0) for e in entidades), default=0)
    dias_atraso_max = max((int(e.get("diasAtrasoPago", 0) or 0) for e in entidades), default=0)

    return BCRAResumen(
        identificacion=str(raw.get("identificacion", "")),
        denominacion=str(raw.get("denominacion", "")),
        periodo=str(ultimo.get("periodo", "")),
        deuda_total_miles=round(deuda_miles, 2),
        deuda_total_pesos=round(deuda_miles * 1000, 2),
        peor_situacion=peor_situacion,
        dias_atraso_max=dias_atraso_max,
        entidades=entidades,
        refinanciaciones=any(bool(e.get("refinanciaciones", False)) for e in entidades),
        recategorizacion_oblig=any(bool(e.get("recategorizacionOblig", False)) for e in entidades),
        situacion_juridica=any(bool(e.get("situacionJuridica", False)) for e in entidades),
        irrec_disposicion_tecnica=any(bool(e.get("irrecDisposicionTecnica", False)) for e in entidades),
        en_revision=any(bool(e.get("enRevision", False)) for e in entidades),
        proceso_jud=any(bool(e.get("procesoJud", False)) for e in entidades),
    )


def parse_cheques_rechazados(raw: Dict[str, Any]) -> ChequesRechazadosResumen:
    cantidad_total = 0
    monto_total = 0.0
    multa_impaga = False
    causales = raw.get("causales", []) or []

    for causal in causales:
        for entidad in causal.get("entidades", []) or []:
            for detalle in entidad.get("detalle", []) or []:
                cantidad_total += 1
                monto_total += float(detalle.get("monto", 0) or 0)
                multa_impaga = multa_impaga or str(detalle.get("estadoMulta", "")).upper() == "IMPAGA"

    return ChequesRechazadosResumen(
        cantidad_total=cantidad_total,
        monto_total=round(monto_total, 2),
        causales=causales,
        multa_impaga=multa_impaga,
    )


def parse_cheque_denunciado(raw: Dict[str, Any]) -> ChequeDenunciadoResultado:
    return ChequeDenunciadoResultado(
        numero_cheque=int(raw.get("numeroCheque", 0) or 0),
        denunciado=bool(raw.get("denunciado", False)),
        fecha_procesamiento=str(raw.get("fechaProcesamiento", "")),
        denominacion_entidad=str(raw.get("denominacionEntidad", "")),
        detalles=raw.get("detalles", []) or [],
    )


# ============================================================
# CÁLCULO DE CUOTA PROPUESTA
# ============================================================
def calcular_cuota_propuesta(cliente: ClienteInput) -> float:
    """
    Calcula automáticamente la cuota propuesta basada en el segmento del cliente.
    
    - Para personas: 35% del sueldo neto
    - Para empresas: Este cálculo requiere categoría tributaria (a definir)
    """
    if cliente.segmento == "persona":
        if cliente.sueldo_neto > 0:
            return cliente.sueldo_neto * 0.35
    # Para empresas, se puede añadir lógica según categoría tributaria
    return 0.0


def generar_observaciones_automaticas(
    cliente: ClienteInput,
    bcra: Optional[BCRAResumen],
    cheques: Optional[ChequesRechazadosResumen],
    afip: Optional[AFIPResumen],
    resultado: ResultadoEvaluacion,
) -> str:
    """
    Genera observaciones automáticas basadas en el análisis financiero
    (BCRA, cheques rechazados, patrimonio y scoring).
    """
    observaciones: List[str] = []
    
    # Análisis de BCRA
    if bcra:
        if bcra.peor_situacion >= 4:
            observaciones.append("Situación BCRA crítica detectada - se requiere revisión exhaustiva")
        elif bcra.deuda_total_pesos > cliente.patrimonio_estimado * 0.5:
            observaciones.append("Deuda BCRA elevada respecto al patrimonio estimado")
        if bcra.dias_atraso_max > 90:
            observaciones.append(f"Máximo de {bcra.dias_atraso_max} días de atraso registrado")
        if bcra.refinanciaciones:
            observaciones.append("Historial de refinanciaciones detectado")
    
    # Análisis de cheques
    if cheques and cheques.cantidad_total > 0:
        observaciones.append(f"{cheques.cantidad_total} cheques rechazados por ${cheques.monto_total:,.2f}")
        if cheques.multa_impaga:
            observaciones.append("Multa por cheques impaga detectada")
    
    # Análisis de AFIP
    if afip:
        if not afip.al_dia:
            observaciones.append("Situación fiscal irregular detectada en AFIP")
        if afip.estado != "ACTIVO":
            observaciones.append(f"Estado AFIP: {afip.estado}")
    else:
        observaciones.append("No se pudo obtener información fiscal de AFIP")
    
    # Análisis de flujo de caja (personas)
    if cliente.segmento == "persona":
        ingreso_neto = cliente.sueldo_neto - cliente.cuotas_existentes
        if cliente.cuota_propuesta > ingreso_neto * 0.35:
            observaciones.append(f"Cuota propuesta ({cliente.cuota_propuesta:,.0f}) alcanza capacidad máxima de pago")
        if cliente.cuota_propuesta + cliente.cuotas_existentes > cliente.sueldo_neto * 0.5:
            observaciones.append("Compromisos de pago total muy elevados")
    
    # Análisis patrimonial
    if cliente.liquidez_inmediata < cliente.cuota_propuesta * 3:
        observaciones.append("Liquidez inmediata insuficiente para 3 meses de cuota")
    
    if cliente.patrimonio_estimado < 0:
        observaciones.append("Alerta: patrimonio estimado negativo")
    
    # Resumen de decisión
    if resultado.decision == "RECHAZAR":
        observaciones.append(f"Recomendación: RECHAZAR - {', '.join(resultado.motivos[:2]) if resultado.motivos else 'ver análisis'}")
    elif resultado.decision == "REVISAR":
        observaciones.append(f"Recomendación: Requiere revisión adicional - Score total: {resultado.score_total:.2f}")
    else:
        observaciones.append(f"Recomendación: APROBAR - Score total: {resultado.score_total:.2f}")
    
    return " | ".join(observaciones) if observaciones else "Análisis completado sin observaciones significativas"



# ============================================================
# MOTOR DE DECISIÓN
# ============================================================
class MotorDecisionBancaria:
    def score_credito(self, cliente: ClienteInput, bcra: Optional[BCRAResumen]) -> Tuple[float, List[str]]:
        if not bcra:
            return 40.0, ["No se pudo obtener información BCRA para crédito."]

        alertas: List[str] = []
        situacion = bcra.peor_situacion
        deuda = bcra.deuda_total_pesos

        score_situacion = {1: 100, 2: 75, 3: 40, 4: 10, 5: 0}.get(situacion, 20)
        if situacion >= 3:
            alertas.append(situacion_label(situacion))

        if cliente.segmento == "persona":
            ingreso_base = cliente.sueldo_neto if cliente.sueldo_neto > 0 else cliente.ingreso_mensual
            ingreso = max(ingreso_base, 1.0)
            cti = (cliente.cuota_propuesta + cliente.cuotas_existentes) / ingreso
            if cti <= 0.25:
                score_capacidad = 100
            elif cti <= 0.35:
                score_capacidad = 75
            elif cti <= 0.45:
                score_capacidad = 45
                alertas.append("CTI exigido.")
            else:
                score_capacidad = 10
                alertas.append("CTI alto.")
        else:
            egresos = max(cliente.egresos_mensuales, 1.0)
            flujo = cliente.ventas_mensuales / egresos
            if flujo >= 1.5:
                score_capacidad = 100
            elif flujo >= 1.2:
                score_capacidad = 75
            elif flujo >= 1.0:
                score_capacidad = 45
                alertas.append("Flujo operativo ajustado.")
            else:
                score_capacidad = 10
                alertas.append("Flujo operativo comprometido.")

        if deuda <= 0:
            score_deuda = 100
        elif deuda <= 500_000:
            score_deuda = 90
        elif deuda <= 5_000_000:
            score_deuda = 65
        elif deuda <= 25_000_000:
            score_deuda = 40
        else:
            score_deuda = 20
            alertas.append("Endeudamiento consolidado elevado.")

        if bcra.proceso_jud:
            alertas.append("Registra proceso judicial.")
            score_situacion = min(score_situacion, 10)
        if bcra.en_revision:
            alertas.append("Información sometida a revisión.")
        if bcra.refinanciaciones:
            alertas.append("Se observan refinanciaciones.")
        if bcra.situacion_juridica:
            alertas.append("Situación jurídica informada.")
        if bcra.irrec_disposicion_tecnica:
            alertas.append("Irrecuperable por disposición técnica.")

        total = (score_situacion * 0.55) + (score_capacidad * 0.25) + (score_deuda * 0.20)
        return round(total, 2), alertas

    def score_cheques(self, cheques: Optional[ChequesRechazadosResumen]) -> Tuple[float, List[str]]:
        if not cheques:
            return 100.0, []

        alertas: List[str] = []
        q = cheques.cantidad_total

        if q == 0:
            score = 100.0
        elif q <= 2:
            score = 70.0
            alertas.append("Antecedentes leves de cheques rechazados.")
        elif q <= 5:
            score = 35.0
            alertas.append("Frecuencia relevante de cheques rechazados.")
        else:
            score = 0.0
            alertas.append("Historial severo de cheques rechazados.")

        if cheques.monto_total > 5_000_000:
            score = min(score, 25.0)
            alertas.append("Monto acumulado rechazado significativo.")
        if cheques.multa_impaga:
            score = min(score, 25.0)
            alertas.append("Se detectan multas impagas asociadas a cheques.")

        return round(score, 2), alertas

    def score_patrimonial(self, cliente: ClienteInput, deuda_total_pesos: float) -> Tuple[float, List[str]]:
        alertas: List[str] = []
        patrimonio = max(cliente.patrimonio_estimado, 0.0)
        liquidez = max(cliente.liquidez_inmediata, 0.0)

        if deuda_total_pesos <= 0:
            score_respaldo = 100.0
        else:
            ratio = patrimonio / deuda_total_pesos
            if ratio >= 3:
                score_respaldo = 100.0
            elif ratio >= 1.5:
                score_respaldo = 75.0
            elif ratio >= 1.0:
                score_respaldo = 45.0
                alertas.append("Respaldo patrimonial ajustado.")
            else:
                score_respaldo = 15.0
                alertas.append("Patrimonio insuficiente frente a deuda.")

        if deuda_total_pesos <= 0:
            score_liquidez = 100.0
        elif liquidez >= deuda_total_pesos * 0.30:
            score_liquidez = 100.0
        elif liquidez >= deuda_total_pesos * 0.15:
            score_liquidez = 70.0
        elif liquidez > 0:
            score_liquidez = 40.0
            alertas.append("Liquidez inmediata baja.")
        else:
            score_liquidez = 20.0
            alertas.append("Sin liquidez inmediata declarada.")

        total = (score_respaldo * 0.75) + (score_liquidez * 0.25)
        return round(total, 2), alertas

    def score_afip(self, afip: Optional[AFIPResumen]) -> Tuple[float, List[str]]:
        if not afip:
            return 50.0, ["No se pudo obtener información AFIP."]

        alertas: List[str] = []
        score = 100.0

        if not afip.al_dia:
            score = 30.0
            alertas.append("Deudas fiscales detectadas en AFIP.")
        elif afip.estado != "ACTIVO":
            score = 60.0
            alertas.append(f"Estado AFIP: {afip.estado}.")
        else:
            alertas.append("Contribuyente al día con AFIP.")

        if not afip.actividades:
            score = min(score, 70.0)
            alertas.append("Sin actividades registradas en AFIP.")

        return round(score, 2), alertas

    def resumir_dictamen(
        self,
        cliente: ClienteInput,
        bcra: Optional[BCRAResumen],
        cheques: Optional[ChequesRechazadosResumen],
        afip: Optional[AFIPResumen],
        resultado: ResultadoEvaluacion,
    ) -> str:
        partes = [
            f"Cliente: {cliente.nombre}.",
            f"Documento: {cliente.documento}.",
        ]
        if bcra:
            partes.append(
                f"Peor situación informada: {situacion_label(bcra.peor_situacion)}. Deuda consolidada estimada: ${bcra.deuda_total_pesos:,.2f}."
            )
        if cheques:
            partes.append(
                f"Cheques rechazados detectados: {cheques.cantidad_total} por un monto total de ${cheques.monto_total:,.2f}."
            )
        if afip:
            partes.append(
                f"Estado AFIP: {afip.estado}. Al día: {'Sí' if afip.al_dia else 'No'}."
            )
        partes.append(f"Score total {resultado.score_total:.2f}. Decisión sugerida: {resultado.decision}.")
        if resultado.motivos:
            partes.append("Alertas principales: " + "; ".join(resultado.motivos[:6]) + ".")
        return " ".join(partes)

    def evaluar(
        self,
        cliente: ClienteInput,
        bcra: Optional[BCRAResumen],
        cheques: Optional[ChequesRechazadosResumen],
        afip: Optional[AFIPResumen],
    ) -> ResultadoEvaluacion:
        motivos: List[str] = []
        score_credito, m1 = self.score_credito(cliente, bcra)
        score_cheques, m2 = self.score_cheques(cheques)
        score_patrimonial, m3 = self.score_patrimonial(cliente, bcra.deuda_total_pesos if bcra else 0.0)
        score_afip, m4 = self.score_afip(afip)
        motivos.extend(m1)
        motivos.extend(m2)
        motivos.extend(m3)
        motivos.extend(m4)

        score_total = round((score_credito * 0.40) + (score_cheques * 0.15) + (score_patrimonial * 0.25) + (score_afip * 0.20), 2)

        if bcra and bcra.peor_situacion >= 4:
            decision: Decision = "RECHAZAR"
            motivos.append("Regla dura: situación BCRA crítica.")
        elif cheques and cheques.cantidad_total >= 6:
            decision = "RECHAZAR"
            motivos.append("Regla dura: historial severo de cheques rechazados.")
        elif not afip or not afip.al_dia:
            decision = "REVISAR"
            motivos.append("Requiere verificación fiscal AFIP.")
        elif score_total >= 80:
            decision = "APROBAR"
        elif score_total >= 55:
            decision = "REVISAR"
        else:
            decision = "RECHAZAR"

        provisional = ResultadoEvaluacion(
            score_total=score_total,
            decision=decision,
            score_credito=score_credito,
            score_cheques=score_cheques,
            score_patrimonial=score_patrimonial,
            score_afip=score_afip,
            motivos=list(dict.fromkeys(motivos)),
        )
        provisional.resumen_llm_style = self.resumir_dictamen(cliente, bcra, cheques, afip, provisional)
        return provisional

def render_login() -> None:
    st.title("Ingreso al sistema")
    st.caption("Acceso restringido")

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar", use_container_width=True):
        user = authenticate_user(username, password)
        if user:
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")

# ============================================================
# UI
# ============================================================
def render_sidebar() -> str:
    st.sidebar.title("Análisis Financiero LumenAnalitica")
    st.sidebar.caption("BCRA + Cheques + Patrimonio + Dictamen")
    return st.sidebar.radio(
        "Módulo",
        [
            "Evaluación integral",
            "Central de deudores",
            "Históricas 24 meses",
            "Cheques rechazados",
            "Cheque denunciado",
            "Historial interno",
        ],
    )


def render_header() -> None:
    st.set_page_config(page_title="Análisis Financiero LumenAnalitica", page_icon="🏦", layout="wide")
    st.title("Análisis Financiero LumenAnalitica")
    st.caption("Herramienta interna para análisis crediticio, cheques, patrimonio y dictamen.")


def render_bcra_deudores() -> None:
    st.subheader("Central de deudores")
    doc = st.text_input("CUIT / CUIL / CDI", key="deudores_doc")
    if st.button("Consultar deuda BCRA", type="primary"):
        if not validar_identificacion(doc):
            st.error("Ingresá 11 dígitos válidos.")
            return
        try:
            raw = bcra_get_deudas(doc)
            resumen = parse_bcra_resumen(raw)
            c1, c2, c3 = st.columns(3)
            with c1:
                metric_card("Peor situación", situacion_label(resumen.peor_situacion))
            with c2:
                metric_card("Deuda consolidada", f"${resumen.deuda_total_pesos:,.2f}")
            with c3:
                metric_card("Máx. días atraso", str(resumen.dias_atraso_max))

            st.markdown("#### Entidades informantes")
            df = pd.DataFrame(resumen.entidades)
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
                dataframe_download_button(df, "Descargar entidades PDF", f"deudores_{clean_doc(doc)}.csv")
            else:
                st.info("Sin entidades para mostrar.")
        except Exception as exc:
            st.error(f"No se pudo consultar BCRA: {exc}")


def render_bcra_historicas() -> None:
    st.subheader("Históricas de deuda")
    doc = st.text_input("CUIT / CUIL / CDI", key="historicas_doc")
    if st.button("Consultar históricas", type="primary"):
        if not validar_identificacion(doc):
            st.error("Ingresá 11 dígitos válidos.")
            return
        try:
            raw = bcra_get_historicas(doc)
            periodos = raw.get("periodos", []) or []
            rows: List[Dict[str, Any]] = []
            for periodo in periodos:
                for entidad in periodo.get("entidades", []) or []:
                    rows.append(
                        {
                            "periodo": periodo.get("periodo", ""),
                            "entidad": entidad.get("entidad", ""),
                            "situacion": entidad.get("situacion", ""),
                            "monto_miles": entidad.get("monto", 0),
                            "en_revision": entidad.get("enRevision", False),
                            "proceso_jud": entidad.get("procesoJud", False),
                        }
                    )
            df = pd.DataFrame(rows)
            if df.empty:
                st.info("Sin información histórica.")
                return

            c1, c2 = st.columns(2)
            with c1:
                metric_card("Períodos", str(df["periodo"].nunique()))
            with c2:
                metric_card("Peor situación histórica", str(df["situacion"].max()))

            serie = df.groupby("periodo", as_index=False)["monto_miles"].sum().sort_values("periodo")
            st.markdown("#### Evolución de deuda (miles de pesos)")
            st.line_chart(serie.set_index("periodo"))
            st.dataframe(
                df.sort_values(["periodo", "situacion"], ascending=[False, False]),
                use_container_width=True,
                hide_index=True,
            )
            dataframe_download_button(df, "Descargar históricas PDF", f"historicas_{clean_doc(doc)}.csv")
        except Exception as exc:
            st.error(f"No se pudo consultar históricas: {exc}")


def render_cheques_rechazados() -> None:
    st.subheader("Cheques rechazados")
    doc = st.text_input("CUIT / CUIL / CDI", key="rechazados_doc")
    if st.button("Consultar cheques rechazados", type="primary"):
        if not validar_identificacion(doc):
            st.error("Ingresá 11 dígitos válidos.")
            return
        try:
            raw = bcra_get_cheques_rechazados(doc)
            resumen = parse_cheques_rechazados(raw)
            c1, c2, c3 = st.columns(3)
            with c1:
                metric_card("Cantidad total", str(resumen.cantidad_total))
            with c2:
                metric_card("Monto total", f"${resumen.monto_total:,.2f}")
            with c3:
                metric_card("Multa impaga", "Sí" if resumen.multa_impaga else "No")

            rows: List[Dict[str, Any]] = []
            for causal in resumen.causales:
                for entidad in causal.get("entidades", []) or []:
                    for detalle in entidad.get("detalle", []) or []:
                        rows.append(
                            {
                                "causal": causal.get("causal", ""),
                                "entidad": entidad.get("entidad", ""),
                                "nro_cheque": detalle.get("nroCheque", ""),
                                "fecha_rechazo": detalle.get("fechaRechazo", ""),
                                "monto": detalle.get("monto", 0),
                                "fecha_pago": detalle.get("fechaPago", ""),
                                "fecha_pago_multa": detalle.get("fechaPagoMulta", ""),
                                "estado_multa": detalle.get("estadoMulta", ""),
                            }
                        )
            df = pd.DataFrame(rows)
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
                dataframe_download_button(df, "Descargar cheques rechazados PDF", f"cheques_rechazados_{clean_doc(doc)}.csv")
            else:
                st.info("Sin detalles para mostrar.")
        except Exception as exc:
            st.error(f"No se pudo consultar cheques rechazados: {exc}")


def render_cheque_denunciado() -> None:
    st.subheader("Cheque denunciado")
    entidades_map: Dict[str, int] = {}
    try:
        entidades = bcra_get_entidades()
        entidades_map = {
            f"{int(e['codigoEntidad'])} - {str(e['denominacion']).strip()}": int(e["codigoEntidad"])
            for e in entidades
        }
    except Exception as exc:
        st.warning(f"No se pudo cargar el maestro de entidades: {exc}")

    entidad_sel = st.selectbox("Entidad bancaria", options=list(entidades_map.keys()) if entidades_map else ["Sin datos"])
    numero_cheque = st.number_input("Número de cheque", min_value=0, step=1, value=0)

    if st.button("Consultar cheque denunciado", type="primary"):
        if not entidades_map:
            st.error("No se pudo obtener el maestro de entidades.")
            return
        codigo_entidad = entidades_map[entidad_sel]
        try:
            raw = bcra_get_cheque_denunciado(codigo_entidad, int(numero_cheque))
            resultado = parse_cheque_denunciado(raw)
            c1, c2, c3 = st.columns(3)
            with c1:
                metric_card("Denunciado", "Sí" if resultado.denunciado else "No")
            with c2:
                metric_card("Entidad", resultado.denominacion_entidad or "-")
            with c3:
                metric_card("Fecha proc.", resultado.fecha_procesamiento or "-")

            df = pd.DataFrame(resultado.detalles)
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
                dataframe_download_button(df, "Descargar detalle PDF", f"cheque_denunciado_{numero_cheque}.csv")
            else:
                st.info("Sin detalles. El cheque no registra denuncia o no hay observaciones.")
        except Exception as exc:
            st.error(f"No se pudo consultar el cheque: {exc}")


def render_historial_interno() -> None:
    st.subheader("Historial interno")
    search = st.text_input("Buscar por CUIT / CUIL / CDI")
    df = load_history(search)
    if df.empty:
        st.info("No hay evaluaciones guardadas.")
        return
    st.dataframe(
        df[[
            "fecha",
            "nombre",
            "documento",
            "segmento",
            "score_total",
            "decision",
            "peor_situacion",
            "cheques_rechazados",
            "deuda_total_pesos",
        ]],
        use_container_width=True,
        hide_index=True,
    )
    dataframe_download_button(df, "Descargar historial PDF", "historial_workbench_credito.csv")


def render_evaluacion_integral() -> None:
    st.subheader("Evaluación integral")
    st.caption("Consulta BCRA, cheques, patrimonio y genera dictamen sugerido.")

    c1, c2, c3 = st.columns(3)
    with c1:
        nombre = st.text_input("Nombre / Razón social")
        documento = st.text_input("CUIT / CUIL / CDI")
        segmento = st.radio("Segmento", ["persona", "empresa"], horizontal=True)
    with c2:
        patrimonio_estimado = st.number_input("Patrimonio estimado", min_value=0.0, step=10000.0, value=0.0)
        liquidez_inmediata = st.number_input("Liquidez inmediata", min_value=0.0, step=10000.0, value=0.0)
    with c3:
        sueldo_neto = st.number_input("Sueldo neto", min_value=0.0, step=10000.0, value=0.0)
        ingreso_mensual = st.number_input("Ingreso mensual total", min_value=0.0, step=10000.0, value=0.0)
        ventas_mensuales = st.number_input("Ventas mensuales", min_value=0.0, step=10000.0, value=0.0)
        egresos_mensuales = st.number_input("Egresos mensuales", min_value=0.0, step=10000.0, value=0.0)
        cuotas_existentes = st.number_input("Cuotas existentes", min_value=0.0, step=1000.0, value=0.0)

    guardar = st.checkbox("Guardar evaluación en historial", value=True)

    if st.button("Evaluar caso", type="primary", use_container_width=True):
        if not nombre.strip():
            st.error("Ingresá nombre o razón social.")
            return
        if not validar_identificacion(documento):
            st.error("Ingresá un CUIT/CUIL/CDI válido de 11 dígitos.")
            return

        # Crear cliente con datos iniciales
        cliente = ClienteInput(
            nombre=nombre.strip(),
            documento=clean_doc(documento),
            segmento=segmento,
            patrimonio_estimado=patrimonio_estimado,
            liquidez_inmediata=liquidez_inmediata,
            sueldo_neto=sueldo_neto,
            ingreso_mensual=ingreso_mensual,
            ventas_mensuales=ventas_mensuales,
            egresos_mensuales=egresos_mensuales,
            cuota_propuesta=0.0,  # Se calcula automáticamente
            cuotas_existentes=cuotas_existentes,
            observaciones="",  # Se generan automáticamente del análisis
        )
        
        # Calcular cuota propuesta automáticamente
        cliente.cuota_propuesta = calcular_cuota_propuesta(cliente)

        bcra: Optional[BCRAResumen] = None
        cheques: Optional[ChequesRechazadosResumen] = None
        afip: Optional[AFIPResumen] = None
        warnings: List[str] = []

        with st.spinner("Consultando BCRA, cheques, AFIP y generando dictamen..."):
            try:
                bcra = parse_bcra_resumen(bcra_get_deudas(cliente.documento))
            except Exception as exc:
                warnings.append(f"No se pudo consultar Central de Deudores: {exc}")
            try:
                cheques = parse_cheques_rechazados(bcra_get_cheques_rechazados(cliente.documento))
            except Exception as exc:
                warnings.append(f"No se pudo consultar Cheques Rechazados: {exc}")
            try:
                afip = parse_afip_resumen(afip_client.get_taxpayer_details(cliente.documento))
            except Exception as exc:
                warnings.append(f"No se pudo consultar AFIP: {exc}")

            motor = MotorDecisionBancaria()
            resultado = motor.evaluar(cliente, bcra, cheques, afip)
            
            # Generar observaciones automáticas del análisis
            cliente.observaciones = generar_observaciones_automaticas(cliente, bcra, cheques, afip, resultado)

        for w in warnings:
            st.warning(w)

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            metric_card("Score total", f"{resultado.score_total:.2f}")
        with m2:
            metric_card("Decisión", resultado.decision)
        with m3:
            metric_card("Situación BCRA", situacion_label(bcra.peor_situacion) if bcra else "No disponible")
        with m4:
            metric_card("Cheques rechazados", str(cheques.cantidad_total if cheques else 0))
        with m5:
            metric_card("Estado AFIP", "Al día" if afip and afip.al_dia else "Pendiente" if afip else "No disponible")

        st.markdown("#### Desglose")
        desglose_df = pd.DataFrame(
            [
                {"factor": "crédito", "score": resultado.score_credito},
                {"factor": "cheques", "score": resultado.score_cheques},
                {"factor": "patrimonial", "score": resultado.score_patrimonial},
                {"factor": "AFIP", "score": resultado.score_afip},
            ]
        )
        st.dataframe(desglose_df, use_container_width=True, hide_index=True)

        st.markdown("#### Dictamen sugerido")
        st.info(resultado.resumen_llm_style)

        st.markdown("#### Alertas")
        if resultado.motivos:
            for motivo in resultado.motivos:
                st.warning(motivo)
        else:
            st.success("Sin alertas relevantes.")

        if bcra and bcra.entidades:
            st.markdown("#### Entidades BCRA")
            st.dataframe(pd.DataFrame(bcra.entidades), use_container_width=True, hide_index=True)

        if cheques and cheques.causales:
            rows: List[Dict[str, Any]] = []
            for causal in cheques.causales:
                for entidad in causal.get("entidades", []) or []:
                    for detalle in entidad.get("detalle", []) or []:
                        rows.append(
                            {
                                "causal": causal.get("causal", ""),
                                "entidad": entidad.get("entidad", ""),
                                "nro_cheque": detalle.get("nroCheque", ""),
                                "fecha_rechazo": detalle.get("fechaRechazo", ""),
                                "monto": detalle.get("monto", 0),
                                "estado_multa": detalle.get("estadoMulta", ""),
                            }
                        )
            if rows:
                st.markdown("#### Detalle de cheques rechazados")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        report = {
            "cliente": asdict(cliente),
            "bcra": asdict(bcra) if bcra else {},
            "cheques": asdict(cheques) if cheques else {},
            "resultado": asdict(resultado),
        }
        json_bytes = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "Descargar informe JSON",
            data=json_bytes,
            file_name=f"informe_credito_{cliente.documento}.json",
            mime="application/json",
            use_container_width=True,
        )

        pdf_bytes = build_pdf_report(cliente, bcra, cheques, resultado)
        st.download_button(
            "Descargar informe PDF",
            data=pdf_bytes,
            file_name=f"informe_credito_{cliente.documento}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

        flat_rows = [
            {"campo": "nombre", "valor": cliente.nombre},
            {"campo": "documento", "valor": cliente.documento},
            {"campo": "segmento", "valor": cliente.segmento},
            {"campo": "sueldo_neto", "valor": cliente.sueldo_neto},
            {"campo": "score_total", "valor": resultado.score_total},
            {"campo": "decision", "valor": resultado.decision},
            {"campo": "score_credito", "valor": resultado.score_credito},
            {"campo": "score_cheques", "valor": resultado.score_cheques},
            {"campo": "score_patrimonial", "valor": resultado.score_patrimonial},
            {"campo": "deuda_total_pesos", "valor": bcra.deuda_total_pesos if bcra else 0},
            {"campo": "peor_situacion", "valor": bcra.peor_situacion if bcra else 0},
            {"campo": "cheques_rechazados", "valor": cheques.cantidad_total if cheques else 0},
            {"campo": "dictamen", "valor": resultado.resumen_llm_style},
        ] + [{"campo": f"alerta_{i+1}", "valor": m} for i, m in enumerate(resultado.motivos)]
        reporte_df = pd.DataFrame(flat_rows)
        dataframe_download_button(reporte_df, "Descargar informe PDF", f"informe_credito_{cliente.documento}.csv")

        if guardar:
            save_eval(cliente, bcra, cheques, afip, resultado)
            st.success("Evaluación guardada en historial.")

def main() -> None:
    init_users_table()

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        render_login()
        return

    render_header()
    st.sidebar.success(
        f"Usuario: {st.session_state['user']['username']} | Rol: {st.session_state['user']['rol']}"
    )

    if st.sidebar.button("Cerrar sesión"):
        st.session_state["logged_in"] = False
        st.session_state.pop("user", None)
        st.rerun()

    module = render_sidebar()
    if module == "Evaluación integral":
        render_evaluacion_integral()
    elif module == "Central de deudores":
        render_bcra_deudores()
    elif module == "Históricas 24 meses":
        render_bcra_historicas()
    elif module == "Cheques rechazados":
        render_cheques_rechazados()
    elif module == "Cheque denunciado":
        render_cheque_denunciado()
    elif module == "Historial interno":
        render_historial_interno()

if __name__ == "__main__":
	main()
