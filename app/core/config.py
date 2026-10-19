from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Meridin Instagram Automation"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "meridin_instagram"
    public_base_url: str = "https://instagram-automation-kx8n.onrender.com"

    jwt_secret: str = "change-me-in-production"
    token_encryption_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    admin_email: str = ""
    admin_password: str = ""

    cors_origins: str = "http://localhost:8000,http://localhost:5173"


    llm_enabled: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_style: str = "responses"
    llm_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: int = 20
    llm_max_output_tokens: int = 700
    tier1_confidence_threshold: float = 0.65
    tier2_confidence_threshold: float = 0.72

    # Optional CLIP image-to-catalogue retrieval; heavyweight dependencies are separate.
    visual_search_enabled: bool = False
    clip_model_name: str = "openai/clip-vit-base-patch32"
    visual_similarity_threshold: float = 0.72
    visual_match_margin: float = 0.035
    visual_image_max_bytes: int = 8 * 1024 * 1024

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
