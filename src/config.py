from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    api_base_url: str
    api_client_id: str
    api_client_secret: str
    api_username: str
    api_password: str
    database_url: str


settings = Settings()
