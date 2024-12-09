from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    plex_base_url: str
    plex_token: str
    client_name: str
    redis_url: str

    class Config:
        env_file = ".env"

settings = Settings()