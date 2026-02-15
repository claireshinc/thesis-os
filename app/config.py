"""Application settings — reads from .env or environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Postgres
    postgres_user: str = "thesis"
    postgres_password: str = "thesis"
    postgres_db: str = "thesis_os"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Anthropic
    anthropic_api_key: str = ""

    # SEC EDGAR
    sec_user_agent: str = "ThesisOS user@example.com"

    # FMP (Financial Modeling Prep)
    fmp_api_key: str = ""

    # OpenBB
    openbb_token: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
