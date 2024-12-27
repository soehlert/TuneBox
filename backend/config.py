"""Config reader for TuneBox."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Define the settings we need."""

    plex_base_url: str
    plex_token: str
    client_name: str
    redis_url: str
    tunebox_url: str

    class Config:
        """Define our settings file."""

        env_file = ".env"


settings = Settings()
