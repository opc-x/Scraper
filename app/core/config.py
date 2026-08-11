from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""

    turso_database_url: str = ""
    turso_auth_token: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    boss_cookie: str = ""

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""

    host: str = "0.0.0.0"
    port: int = 80
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
