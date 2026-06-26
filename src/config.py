from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    api_base_url: str
    api_client_id: str
    api_client_secret: str
    api_username: str
    api_password: str
    database_url: str

    @property
    def db_path(self) -> str:
        """Return a plain filesystem path from the SQLAlchemy-style DATABASE_URL."""
        url = self.database_url
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///") :]
        if url.startswith("sqlite://"):
            return url[len("sqlite://") :]
        return url


settings = Settings()
