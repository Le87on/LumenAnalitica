from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Segmento = Literal["persona", "empresa"]
Decision = Literal["APROBAR", "REVISAR", "RECHAZAR"]


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    username: Optional[str] = None
    rol: Optional[str] = None
    error: Optional[str] = None


class ClienteInput(BaseModel):
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


class BCRAResumen(BaseModel):
    identificacion: str = ""
    denominacion: str = ""
    periodo: str = ""
    deuda_total_miles: float = 0.0
    deuda_total_pesos: float = 0.0
    peor_situacion: int = 0
    dias_atraso_max: int = 0
    entidades: List[Dict[str, Any]] = Field(default_factory=list)
    refinanciaciones: bool = False
    recategorizacion_oblig: bool = False
    situacion_juridica: bool = False
    irrec_disposicion_tecnica: bool = False
    en_revision: bool = False
    proceso_jud: bool = False


class ChequesRechazadosResumen(BaseModel):
    cantidad_total: int = 0
    monto_total: float = 0.0
    causales: List[Dict[str, Any]] = Field(default_factory=list)
    multa_impaga: bool = False


class ResultadoEvaluacion(BaseModel):
    score_total: float
    decision: Decision
    score_credito: float
    score_cheques: float
    score_patrimonial: float
    motivos: List[str] = Field(default_factory=list)
    resumen_llm_style: str = ""
