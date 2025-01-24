"""Config reader for TuneBox."""

from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import BaseModel


class Settings(BaseSettings):
    """Define the settings we need."""

    plex_username: str
    plex_password: str
    plex_server_name: Optional[str] = None
    client_name: Optional[str] = None
    redis_url: str
    tunebox_url: str

    class Config:
        """Define our settings file."""

        env_file = ".env"


class UserSettings(BaseModel):
    """Define our user configurable settings."""
    plex_server_name: Optional[str]
    client_name: Optional[str]


settings = Settings()
