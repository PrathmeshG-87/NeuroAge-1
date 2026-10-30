from __future__ import annotations

from functools import lru_cache
import ipaddress
from pathlib import Path
import secrets

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = Field(default='NeuroAge API', alias='APP_NAME')
    app_version: str = Field(default='0.1.0', alias='APP_VERSION')
    environment: str = Field(default='development', alias='ENVIRONMENT')
    debug: bool = Field(default=False, alias='DEBUG')
    host: str = Field(default='127.0.0.1', alias='HOST')
    port: int = Field(default=8000, alias='PORT')
    secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(48),
        alias='JWT_SECRET_KEY',
        min_length=32,
    )
    access_token_expire_minutes: int = Field(
        default=30, alias='ACCESS_TOKEN_EXPIRE_MINUTES', gt=0, le=1440
    )
    jwt_issuer: str = Field(default='neuroage-local', alias='JWT_ISSUER')
    jwt_audience: str = Field(default='neuroage', alias='JWT_AUDIENCE')
    database_url: str = Field(
        default_factory=lambda: (
            f"sqlite:///{(BACKEND_ROOT / 'storage' / 'neuroage.db').as_posix()}"
        ),
        alias='DATABASE_URL',
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ['http://localhost:4173', 'http://localhost:5173', 'http://localhost:3000'],
        alias='CORS_ORIGINS',
    )
    model_service_url: str = Field(default='http://localhost:8001', alias='MODEL_SERVICE_URL')
    model_artifact_path: str | None = Field(
        default_factory=lambda: str(BACKEND_ROOT / 'storage' / 'models' / 'neuroage_3d_resnet18' / 'best_model.pth'),
        alias='MODEL_ARTIFACT_PATH',
    )
    model_name: str = Field(default='NeuroAge-ResNet3D-18', alias='MODEL_NAME')
    model_version: str = Field(default='kaggle-ixi-2026-10', alias='MODEL_VERSION')
    evaluation_metrics_path: str | None = Field(
        default_factory=lambda: str(BACKEND_ROOT / 'storage' / 'models' / 'neuroage_3d_resnet18' / 'evaluation_metrics.json'),
        alias='MODEL_EVALUATION_METRICS_PATH',
    )
    upload_directory: str = Field(default='./storage/uploads', alias='UPLOAD_DIRECTORY')
    report_directory: str = Field(default='./storage/reports', alias='REPORT_DIRECTORY')
    dataset_root: str = Field(default='./data/raw', alias='DATASET_ROOT')
    dataset_metadata_path: str | None = Field(default=None, alias='DATASET_METADATA_PATH')
    dataset_derived_dir: str = Field(default='./data/derived', alias='DATASET_DERIVED_DIR')
    max_upload_size_bytes: int = Field(default=250 * 1024 * 1024, alias='MAX_UPLOAD_SIZE_BYTES')
    max_decoded_voxels: int = Field(default=32_000_000, alias='MAX_DECODED_VOXELS')
    upload_retention_days: int = Field(default=30, alias='UPLOAD_RETENTION_DAYS')
    report_retention_days: int = Field(default=30, alias='REPORT_RETENTION_DAYS')
    authentication_required: bool = Field(default=False, alias='AUTHENTICATION_REQUIRED')
    trusted_proxy_ips: list[str] = Field(default_factory=list, alias='TRUSTED_PROXY_IPS')
    rate_limit_per_minute: int = Field(default=30, alias='RATE_LIMIT_PER_MINUTE')
    max_request_body_bytes: int = Field(default=251 * 1024 * 1024, alias='MAX_REQUEST_BODY_BYTES')
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / '.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
        protected_namespaces=(),
    )

    @field_validator('cors_origins', mode='before')
    @classmethod
    def parse_cors_origins(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('trusted_proxy_ips', mode='before')
    @classmethod
    def parse_trusted_proxy_ips(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value

    @field_validator('trusted_proxy_ips')
    @classmethod
    def validate_trusted_proxy_ips(cls, value):
        for item in value:
            ipaddress.ip_network(item, strict=False)
        return value

    @field_validator('secret_key')
    @classmethod
    def reject_example_secret(cls, value: str) -> str:
        if value.lower().startswith('replace_with_'):
            raise ValueError(
                'Remove the example JWT_SECRET_KEY and provide a generated secret.'
            )
        return value

    @model_validator(mode='after')
    def require_production_secret(self) -> Settings:
        if self.is_production and 'secret_key' not in self.model_fields_set:
            raise ValueError(
                'JWT_SECRET_KEY must be configured explicitly in production.'
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == 'production'

    @property
    def cors_allowlist(self) -> list[str]:
        return self.cors_origins


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
