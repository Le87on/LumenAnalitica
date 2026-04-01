# Auditoría técnica (modo producción bancaria)

Fecha: 2026-04-01
Alcance: revisión estática de `app.py`, `config.py`, scripts AFIP y documentación operativa.

## Hallazgos críticos

1. **Autenticación inválida por uso incorrecto de bcrypt (CRÍTICO).**
   - Se comparaba `password_hash` contra `hash_password(password)` en SQL.
   - Con bcrypt (salt aleatorio), este flujo no permite login correcto y puede inducir workarounds inseguros.
   - **Estado:** corregido en `app.py` usando lectura de hash almacenado + `verify_password`.

2. **Ruptura de navegación por nombres de funciones inexistentes (CRÍTICO).**
   - En `main()` se invocaban funciones con nombres distintos a los definidos (errores de `NameError`).
   - **Estado:** corregido mapeando cada módulo al nombre real.

3. **Ruptura en módulo de cheques denunciados por nombres inconsistentes (CRÍTICO).**
   - Se llamaban `bcra_get_cheques_denunciados` y `parse_cheques_denunciados`, pero las funciones reales eran singulares.
   - **Estado:** corregido.

4. **Error de sintaxis/indentación en inicialización de usuarios (CRÍTICO).**
   - `IndentationError` impedía compilar/ejecutar el módulo.
   - **Estado:** corregido.

## Hallazgos altos

1. **Inconsistencia de dominio de datos para `segmento` (ALTO).**
   - La UI entregaba `Persona Fisica/Persona Juridica`, pero el motor espera `persona/empresa`.
   - Esto alteraba scoring (branch incorrecto) y decisiones de riesgo.
   - **Estado:** corregido con normalización explícita.

2. **Credencial por defecto insegura en configuración general (ALTO).**
   - `STREAMLIT_SECRET_KEY` tiene fallback a valor fijo de desarrollo.
   - Recomendación: exigir variable obligatoria en producción y fallar al arranque si no existe.

## Hallazgos medios

1. **Manejo amplio de excepciones (`except:`) en lectura de secrets.**
   - Reduce observabilidad y puede ocultar problemas de configuración.
   - Recomendación: capturar excepciones específicas y loggear causa.

2. **Acoplamiento UI/Lógica de red en rutas críticas.**
   - Aunque hay capas de parseo y motor, aún existen side effects de UI (`st.info/warning`) en flujos de consulta.
   - Recomendación: mover notificaciones fuera de clientes y retornar errores tipados.

## Recomendaciones priorizadas

1. Agregar suite mínima de tests:
   - autenticación (`verify_password`),
   - ruteo de módulos,
   - decisión crediticia con casos borde.
2. Establecer validaciones de arranque (config obligatoria en producción).
3. Añadir CI con `python -m py_compile`, `pytest`, `ruff`/`flake8`.
4. Definir políticas de secretos (sin defaults inseguros) y rotación.

