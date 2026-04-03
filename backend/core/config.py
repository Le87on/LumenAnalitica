from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LumenAnalitica API"
    app_env: str = "dev"
    app_debug: bool = True
    database_path: str = "./lumen_stage1.db"
    bootstrap_user: str = ""
    bootstrap_password: str = ""
    bootstrap_role: str = "admin"
    bcra_base_url: str = "https://api.bcra.gob.ar"
    bcra_timeout: int = 15
    backend_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
