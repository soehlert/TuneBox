"""Config reader for TuneBox."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Define the settings we need."""

    plex_username: str
    plex_password: str
    plex_server_name: str
    client_name: str
    redis_url: str
    tunebox_url: str

    class Config:
        """Define our settings file."""

        env_file = ".env"


settings = Settings()
