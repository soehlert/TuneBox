"""Config reader for TuneBox."""

import os
import pathlib

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file_path(data_dir: str | None = None) -> str:
    """Resolve the path to the .env file, honoring DATA_DIR when set."""
    target_dir = data_dir if data_dir is not None else os.getenv("DATA_DIR", "").strip()
    if target_dir:
        dir_path = pathlib.Path(target_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        return str(dir_path / ".env")
    return ".env"


class Settings(BaseSettings):
    """Define the settings we need."""

    data_dir: str = ""
    plex_username: str = ""
    plex_password: str = ""
    plex_token: str = ""
    plex_server_name: str = ""
    client_name: str = ""
    instance_name: str = "TuneBox"
    redis_url: str = "redis://redis:6379"
    tunebox_url: str = ""
    testing: bool = False
    admin_token: str = ""
    index_interval_hours: float = 24.0

    model_config = SettingsConfigDict(env_file=get_env_file_path(), extra="ignore")


settings = Settings(_env_file=get_env_file_path())
