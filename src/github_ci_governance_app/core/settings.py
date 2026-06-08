from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from github_ci_governance_app.domain.governance_models import RetryPolicy


class Settings(BaseSettings):
    app_name: str = Field(default="github-ci-governance-app", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    github_app_id: int = Field(alias="GITHUB_APP_ID")
    github_webhook_secret: str = Field(alias="GITHUB_WEBHOOK_SECRET")
    github_private_key: str = Field(default="", alias="GITHUB_PRIVATE_KEY")
    github_private_key_path: str = Field(default="", alias="GITHUB_PRIVATE_KEY_PATH")
    github_api_url: str = Field(default="https://api.github.com", alias="GITHUB_API_URL")
    github_allowed_events: str = Field(
        default="push,pull_request,installation,workflow_run",
        alias="GITHUB_ALLOWED_EVENTS",
    )
    basic_validation_workflow: str = Field(
        default="basic-validation.yml",
        alias="BASIC_VALIDATION_WORKFLOW",
    )
    heavy_validation_workflow: str = Field(
        default="heavy-validation.yml",
        alias="HEAVY_VALIDATION_WORKFLOW",
    )
    retry_max_attempts: int = Field(default=3, alias="RETRY_MAX_ATTEMPTS")
    retry_base_delay_seconds: float = Field(default=0.5, alias="RETRY_BASE_DELAY_SECONDS")
    retry_max_delay_seconds: float = Field(default=8.0, alias="RETRY_MAX_DELAY_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @property
    def allowed_events(self) -> set[str]:
        return {event.strip() for event in self.github_allowed_events.split(",") if event.strip()}

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=self.retry_max_attempts,
            base_delay_seconds=self.retry_base_delay_seconds,
            max_delay_seconds=self.retry_max_delay_seconds,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

# Made with Bob
