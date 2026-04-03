from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from backend.models.schemas import BCRAResumen, ChequesRechazadosResumen, ClienteInput, ResultadoEvaluacion



def situacion_label(situacion: int) -> str:
    return {
        1: "Situación 1: Normal",
        2: "Situación 2: Riesgo bajo / seguimiento especial",
        3: "Situación 3: Con problemas / riesgo medio",
        4: "Situación 4: Alto riesgo",
        5: "Situación 5: Irrecuperable",
    }.get(int(situacion or 0), "Situación no informada")



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


class MotorDecisionBancaria:
    def score_credito(self, cliente: ClienteInput, bcra: Optional[BCRAResumen]) -> Tuple[float, List[str]]:
        if not bcra:
            return 40.0, ["No se pudo obtener información BCRA para crédito."]

        alertas: List[str] = []
        score_situacion = {1: 100, 2: 75, 3: 40, 4: 10, 5: 0}.get(bcra.peor_situacion, 20)
        if bcra.peor_situacion >= 3:
            alertas.append(situacion_label(bcra.peor_situacion))

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
            flujo = cliente.ventas_mensuales / egresos if egresos > 0 else 0
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

        deuda = bcra.deuda_total_pesos
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
            ratio = patrimonio / deuda_total_pesos if deuda_total_pesos > 0 else 0
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

    def evaluar(
        self,
        cliente: ClienteInput,
        bcra: Optional[BCRAResumen],
        cheques: Optional[ChequesRechazadosResumen],
    ) -> ResultadoEvaluacion:
        motivos: List[str] = []
        score_credito, m1 = self.score_credito(cliente, bcra)
        score_cheques, m2 = self.score_cheques(cheques)
        score_patrimonial, m3 = self.score_patrimonial(cliente, bcra.deuda_total_pesos if bcra else 0.0)
        motivos.extend(m1)
        motivos.extend(m2)
        motivos.extend(m3)

        score_total = round((score_credito * 0.50) + (score_cheques * 0.20) + (score_patrimonial * 0.30), 2)

        if bcra and bcra.peor_situacion >= 4:
            decision = "RECHAZAR"
            motivos.append("Regla dura: situación BCRA crítica.")
        elif cheques and cheques.cantidad_total >= 6:
            decision = "RECHAZAR"
            motivos.append("Regla dura: historial severo de cheques rechazados.")
        elif score_total >= 80:
            decision = "APROBAR"
        elif score_total >= 55:
            decision = "REVISAR"
        else:
            decision = "RECHAZAR"

        resumen = (
            f"Cliente: {cliente.nombre}. Documento: {cliente.documento}. "
            f"Score total {score_total:.2f}. Decisión sugerida: {decision}."
        )
        return ResultadoEvaluacion(
            score_total=score_total,
            decision=decision,
            score_credito=score_credito,
            score_cheques=score_cheques,
            score_patrimonial=score_patrimonial,
            motivos=list(dict.fromkeys(motivos)),
            resumen_llm_style=resumen,
        )
