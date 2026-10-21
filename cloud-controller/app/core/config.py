"""Application configuration.

All settings come from environment variables / a `.env` file (see `.env.example`).
Nothing machine specific (IP addresses, credentials) is hardcoded here.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- application -------------------------------------------------------
    app_name: str = "LAN SaaS Cloud Storage"
    environment: Literal["development", "test", "production"] = "development"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- security ----------------------------------------------------------
    jwt_secret: str = "insecure-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60

    # --- database ----------------------------------------------------------
    database_url: str = "sqlite:///./lan_saas.db"

    # --- uploads -----------------------------------------------------------
    max_upload_bytes: int = 10 * 1024 * 1024
    max_files_per_user: int = 500

    # --- rate limiting -----------------------------------------------------
    auth_rate_limit_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60

    # --- HDFS --------------------------------------------------------------
    hdfs_adapter: Literal["webhdfs", "mock"] = "webhdfs"
    hdfs_base_url: str = "http://localhost:9870"
    hdfs_service_user: str = "saascloud"
    hdfs_auth: Literal["simple"] = "simple"
    hdfs_root: str = "/saas-cloud"
    hdfs_timeout_seconds: float = 15.0
    hdfs_jmx_url: str = ""
    hdfs_mock_dir: str = "./mock_hdfs_data"
    # Octal permissions applied by the controller (least privilege).
    hdfs_dir_permission: str = "0750"
    hdfs_file_permission: str = "0640"

    # --- first admin bootstrap --------------------------------------------
    admin_bootstrap_username: str = ""
    admin_bootstrap_password: str = ""

    # --- optional static frontend -----------------------------------------
    static_dir: str = ""

    # ----------------------------------------------------------------------
    @field_validator("hdfs_root")
    @classmethod
    def _normalise_root(cls, v: str) -> str:
        v = "/" + v.strip().strip("/")
        if v == "/":
            raise ValueError("HDFS_ROOT must not be the filesystem root '/'")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_mock_hdfs(self) -> bool:
        return self.hdfs_adapter == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
