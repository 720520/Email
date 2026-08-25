"""应用配置加载与校验。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"


class AppSettings(BaseModel):
    """Web 应用配置。"""

    name: str = "基金运营邮件自动解析与净值汇总系统"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        prefix = value.strip().rstrip("/")
        if not prefix.startswith("/"):
            raise ValueError("api_prefix 必须以 / 开头")
        return prefix


class DatabaseSettings(BaseModel):
    """数据库连接配置。"""

    url: str = "sqlite:///./data/fund_nav.db"
    echo: bool = False


class LoggingSettings(BaseModel):
    """日志输出与滚动策略。"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    directory: Path = Path("logs")
    filename: str = "backend.log"
    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    backup_count: int = Field(default=10, ge=1, le=100)


class EmailSettings(BaseModel):
    """IMAP 邮箱读取、安全限制与重试配置。"""

    host: str = ""
    port: int = Field(default=993, ge=1, le=65535)
    username: str = ""
    auth_mode: Literal["password", "oauth2"] = "password"
    password: SecretStr = SecretStr("")
    oauth2_access_token: SecretStr = SecretStr("")
    use_ssl: bool = True
    start_tls: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    folder: str = "INBOX"
    lookback_days: int = Field(default=7, ge=1, le=365)
    max_messages_per_run: int = Field(default=200, ge=1, le=5000)
    max_attachment_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    max_raw_message_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)
    max_attachments_per_email: int = Field(default=30, ge=1, le=500)
    max_total_attachment_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)
    retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_delay_seconds: float = Field(default=1.0, ge=0, le=60)
    uid_reservation_stale_seconds: int = Field(default=1800, ge=60, le=86400)
    candidate_keywords: list[str] = Field(
        default_factory=lambda: ["基金净值", "每日净值", "净值表", "资产净值"]
    )
    excel_extensions: list[str] = Field(default_factory=lambda: [".xls", ".xlsx"])

    @model_validator(mode="after")
    def validate_transport_security(self) -> EmailSettings:
        if self.use_ssl and self.start_tls:
            raise ValueError("use_ssl 与 start_tls 不能同时启用")
        return self


class SchedulerSettings(BaseModel):
    """调度参数；具体任务在后续阶段接入。"""

    enabled: bool = False
    timezone: str = "Asia/Shanghai"
    daily_hour: int = Field(default=18, ge=0, le=23)
    daily_minute: int = Field(default=0, ge=0, le=59)


class ExcelSettings(BaseModel):
    """Excel表头扫描、数据终止和字段词典配置。"""

    field_alias_file: Path = Path("config/excel_fields.yaml")
    header_scan_rows: int = Field(default=40, ge=5, le=200)
    max_header_rows: int = Field(default=3, ge=1, le=5)
    min_header_fields: int = Field(default=2, ge=1, le=10)
    ambiguity_score_delta: float = Field(default=5.0, ge=0, le=50)
    max_consecutive_blank_rows: int = Field(default=20, ge=1, le=200)
    max_columns: int = Field(default=100, ge=5, le=1000)
    max_workbook_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    max_sheets: int = Field(default=50, ge=1, le=500)
    max_rows_per_sheet: int = Field(default=100_000, ge=100, le=1_000_000)
    max_total_cells: int = Field(default=2_000_000, ge=1000, le=100_000_000)
    max_xlsx_uncompressed_bytes: int = Field(default=250 * 1024 * 1024, ge=1024)
    max_xlsx_compression_ratio: float = Field(default=100.0, ge=1.0, le=10_000.0)
    parser_version: str = Field(default="2026.08.25.1", min_length=1, max_length=64)
    worker_concurrency: int = Field(default=1, ge=1, le=8)
    worker_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    worker_stale_minutes: int = Field(default=15, ge=1, le=1440)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    footer_markers: list[str] = Field(
        default_factory=lambda: [
            "声明",
            "免责声明",
            "风险提示",
            "重要提示",
            "特别提示",
            "保密声明",
            "confidential note",
            "disclaimer",
        ]
    )


class StorageSettings(BaseModel):
    """归档与导出数据根目录。"""

    data_directory: Path = Path("data")
    archive_timezone: str = "Asia/Shanghai"
    daily_export_filename: str = "每日基金净值汇总.xlsx"
    max_filing_file_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)

    @field_validator("daily_export_filename")
    @classmethod
    def validate_daily_export_filename(cls, value: str) -> str:
        filename = value.strip()
        if not filename or Path(filename).name != filename:
            raise ValueError("daily_export_filename 必须是文件名，不能包含目录")
        if Path(filename).suffix.casefold() != ".xlsx":
            raise ValueError("daily_export_filename 必须使用 .xlsx 扩展名")
        return filename


class ReportSettings(BaseModel):
    """合同与报表模板上传限制。"""

    max_contract_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)
    max_template_bytes: int = Field(default=150 * 1024 * 1024, ge=1024)
    worker_concurrency: int = Field(default=2, ge=1, le=16)
    worker_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    worker_stale_minutes: int = Field(default=15, ge=1, le=1440)


class OnlyOfficeSettings(BaseModel):
    """ONLYOFFICE Document Server 连接与短期文件授权。"""

    enabled: bool = False
    public_url: str = "http://127.0.0.1:8080"
    internal_url: str = "http://127.0.0.1:8080"
    callback_base_url: str = "http://host.docker.internal:8000"
    jwt_secret: SecretStr = SecretStr("")
    request_timeout: float = Field(default=5.0, ge=0.5, le=60)
    max_download_bytes: int = Field(default=200 * 1024 * 1024, ge=1024)
    file_token_ttl_seconds: int = Field(default=300, ge=30, le=3600)


class SecuritySettings(BaseModel):
    """本地管理后台的会话安全配置。"""

    secret_key: SecretStr = SecretStr("development-only-secret-change-me")
    credential_encryption_key: SecretStr = SecretStr("")
    audit_signing_key: SecretStr = SecretStr("")
    session_cookie_name: str = "fund_nav_session"
    session_ttl_minutes: int = Field(default=480, ge=15, le=10080)
    secure_cookie: bool = False

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 24:
            raise ValueError("security.secret_key 至少需要 24 个字符")
        return value

    @field_validator("session_cookie_name")
    @classmethod
    def validate_cookie_name(cls, value: str) -> str:
        name = value.strip()
        if not name or not name.replace("_", "").isalnum():
            raise ValueError("session_cookie_name 只能包含字母、数字和下划线")
        return name


class Settings(BaseSettings):
    """应用总配置。

    优先级为环境变量、.env、YAML、默认值。这样生产环境可以安全覆盖
    YAML 中的非敏感默认配置。
    """

    model_config = SettingsConfigDict(
        env_prefix="FUND_NAV_",
        env_nested_delimiter="__",
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    excel: ExcelSettings = Field(default_factory=ExcelSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    reports: ReportSettings = Field(default_factory=ReportSettings)
    onlyoffice: OnlyOfficeSettings = Field(default_factory=OnlyOfficeSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        secret = self.security.secret_key.get_secret_value()
        if self.app.environment == "production" and (
            secret == "development-only-secret-change-me" or len(secret) < 32
        ):
            raise ValueError("生产环境必须通过环境变量配置至少 32 位的 security.secret_key")
        if self.app.environment == "production" and not (
            self.security.credential_encryption_key.get_secret_value()
            and self.security.audit_signing_key.get_secret_value()
        ):
            raise ValueError("生产环境必须分别配置邮箱凭据加密密钥和审计签名密钥")
        if self.onlyoffice.enabled and len(self.onlyoffice.jwt_secret.get_secret_value()) < 32:
            raise ValueError("OnlyOffice 启用时必须配置至少 32 位独立 JWT 密钥")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del settings_cls
        return env_settings, dotenv_settings, init_settings, file_secret_settings

    def resolve_path(self, value: Path) -> Path:
        """将相对路径稳定地解析到项目根目录。"""

        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @property
    def data_directory(self) -> Path:
        return self.resolve_path(self.storage.data_directory)

    @property
    def log_directory(self) -> Path:
        return self.resolve_path(self.logging.directory)

    @property
    def excel_field_alias_file(self) -> Path:
        return self.resolve_path(self.excel.field_alias_file)

    @property
    def database_url(self) -> str:
        """将相对 SQLite 文件路径转换为绝对路径，避免受启动目录影响。"""

        prefix = "sqlite:///"
        if not self.database.url.startswith(prefix):
            return self.database.url

        raw_path = self.database.url[len(prefix) :]
        if raw_path == ":memory:" or raw_path.startswith("/"):
            return self.database.url

        absolute_path = (PROJECT_ROOT / raw_path).resolve()
        return f"{prefix}{absolute_path.as_posix()}"


def _read_yaml_config(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"配置文件 YAML 格式错误: {path}") from exc

    if not isinstance(content, dict):
        raise ValueError(f"配置文件顶层必须是映射对象: {path}")
    return content


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """加载并缓存配置，确保应用生命周期内配置一致。"""

    configured_path = os.getenv("FUND_NAV_CONFIG_FILE")
    config_path = Path(configured_path) if configured_path else DEFAULT_CONFIG_FILE
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    return Settings(**_read_yaml_config(config_path.resolve()))
