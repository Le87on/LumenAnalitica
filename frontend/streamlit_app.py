from __future__ import annotations

import requests
import streamlit as st

from backend.core.config import settings


API_BASE = settings.backend_url



def login_view() -> None:
    st.title("LumenAnalitica")
    st.caption("Etapa 1 — frontend desacoplado")

    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar", use_container_width=True):
        try:
            response = requests.post(
                f"{API_BASE}/auth/login",
                json={"username": username, "password": password},
                timeout=20,
            )
            data = response.json()
            if data.get("ok"):
                st.session_state["logged_in"] = True
                st.session_state["user"] = {
                    "username": data["username"],
                    "rol": data["rol"],
                }
                st.rerun()
            st.error(data.get("error", "Credenciales inválidas"))
        except Exception as exc:
            st.error(f"No se pudo conectar con el backend: {exc}")



def home_view() -> None:
    st.title("LumenAnalitica")
    user = st.session_state["user"]
    st.sidebar.success(f"{user['username']} | {user['rol']}")

    if st.sidebar.button("Cerrar sesión"):
        st.session_state.pop("logged_in", None)
        st.session_state.pop("user", None)
        st.rerun()

    st.subheader("Estado del backend")
    try:
        response = requests.get(f"{API_BASE}/health", timeout=20)
        st.json(response.json())
    except Exception as exc:
        st.error(f"Backend no disponible: {exc}")

    st.info("Etapa 1 lista. En la Etapa 2 migramos auth + auditoría + BCRA a endpoints reales.")



def main() -> None:
    st.set_page_config(page_title="LumenAnalitica", page_icon="🏦", layout="wide")
    if not st.session_state.get("logged_in"):
        login_view()
        return
    home_view()


if __name__ == "__main__":
    main()
