"""
Central configuration. Loaded once via pydantic-settings from environment
variables / .env file. Nothing here should ever hold a literal secret —
values come from the environment so real deployments can inject them via
a secrets manager.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # General
    app_env: str = "local"
    demo_mode: bool = True
    emergency_mode: bool = False
    log_level: str = "INFO"

    # Postgres
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "vote_research_demo"

    postgres_eligibility_user: str = "role_eligibility_svc"
    postgres_eligibility_password: str = ""
    postgres_ballot_user: str = "role_ballot_svc"
    postgres_ballot_password: str = ""
    postgres_admin_user: str = "role_admin_svc"
    postgres_admin_password: str = ""
    postgres_analytics_user: str = "role_analytics_svc"
    postgres_analytics_password: str = ""
    postgres_auditor_user: str = "role_auditor_svc"
    postgres_auditor_password: str = ""

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # JWT
    jwt_secret_key: str = "dev-only-not-secure-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15

    # Voting token
    voting_token_expire_minutes: int = 15
    voting_token_bytes: int = 32

    # Rate limiting
    rate_limit_login_attempts: int = 5
    rate_limit_login_window_seconds: int = 900
    rate_limit_ballot_attempts: int = 10
    rate_limit_ballot_window_seconds: int = 60

    # CORS
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:8501"

    def db_url(self, user: str, password: str) -> str:
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def eligibility_db_url(self) -> str:
        return self.db_url(self.postgres_eligibility_user, self.postgres_eligibility_password)

    @property
    def ballot_db_url(self) -> str:
        return self.db_url(self.postgres_ballot_user, self.postgres_ballot_password)

    @property
    def admin_db_url(self) -> str:
        return self.db_url(self.postgres_admin_user, self.postgres_admin_password)

    @property
    def analytics_db_url(self) -> str:
        return self.db_url(self.postgres_analytics_user, self.postgres_analytics_password)

    @property
    def auditor_db_url(self) -> str:
        return self.db_url(self.postgres_auditor_user, self.postgres_auditor_password)

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
