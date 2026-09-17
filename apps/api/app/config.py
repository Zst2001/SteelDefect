from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_repo_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mysql_dsn: str = "mysql+pymysql://lab:labdev_mysql@127.0.0.1:3306/steel_lab?charset=utf8mb4"
    redis_queue_url: str = "redis://127.0.0.1:6379/0"
    redis_cache_url: str = "redis://127.0.0.1:6379/1"
    secret_key: str = "change-me-local-dev-secret-not-for-production"
    session_hours: int = 24
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174"
    storage_root: str = "storage"
    seed_on_start: bool = True
    seed_advisor_username: str = "advisor"
    seed_advisor_password: str = "AdvisorDev!234"
    seed_student_username: str = "student"
    seed_student_password: str = "StudentDev!234"
    max_upload_images: int = 50
    max_image_bytes: int = 20 * 1024 * 1024
    compare_job_timeout_sec: int = 7200
    eval_job_timeout_sec: int = 7200
    eval_montage_samples: int = 8
    cache_task_ttl_sec: int = 60
    cache_models_ttl_sec: int = 600
    session_cookie_name: str = "lab_session"
    rq_queue_name: str = "lab"
    max_py_bytes: int = 256 * 1024
    max_pth_bytes: int = 512 * 1024 * 1024
    admit_job_timeout_sec: int = 600
    student_infer_timeout_sec: int = 900
    student_image: str = "steel-lab-student:cpu"

    @property
    def repo_root(self) -> Path:
        return _repo_root()

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_root)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
