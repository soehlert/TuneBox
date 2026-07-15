"""Config reader for TuneBox."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Define the settings we need."""

    plex_username: str = ""
    plex_password: str = ""
    plex_token: str = ""
    plex_server_name: str = ""
    client_name: str = ""
    redis_url: str = "redis://redis:6379"
    tunebox_url: str = ""
    testing: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
