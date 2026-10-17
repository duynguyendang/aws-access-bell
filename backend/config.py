import os
from dataclasses import dataclass, field


def _load_env_file() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


_load_env_file()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _db_url() -> str:
    explicit = _env("DB_URL")
    if explicit:
        return explicit
    pg_host = _env("POSTGRES_HOST") or _env("DB_HOST")
    if pg_host:
        pg_user = _env("POSTGRES_USER") or _env("DB_USER", "accessbell")
        pg_pw = _env("POSTGRES_PASSWORD") or _env("DB_PASSWORD", "")
        pg_port = _env("POSTGRES_PORT") or _env("DB_PORT", "5432")
        pg_db = _env("POSTGRES_DB") or _env("DB_NAME", "accessbell")
        return f"postgresql://{pg_user}:{pg_pw}@{pg_host}:{pg_port}/{pg_db}"
    return f"sqlite:///{_env('DB_PATH', 'accessbell.db')}"


def _api_auth_disabled() -> bool:
    raw = os.getenv("API_AUTH_DISABLED")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return not bool(os.getenv("API_TOKEN"))


@dataclass
class Settings:
    mock_mode: bool = field(default_factory=lambda: _flag("MOCK_MODE", True))
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "stub").lower())
    db_url: str = field(default_factory=_db_url)
    db_path: str = field(default_factory=lambda: _env("DB_PATH", "accessbell.db"))
    web_dir: str = field(default_factory=lambda: _env("WEB_DIR", "web"))
    mock_events_dir: str = field(default_factory=lambda: _env("MOCK_EVENTS_DIR", "mock/events"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO").upper())

    ring_webhook_enabled: bool = field(default_factory=lambda: _flag("RING_WEBHOOK_ENABLED", False))
    ring_secret: str = field(default_factory=lambda: _env("RING_WEBHOOK_SECRET"))
    ring_signature_header: str = field(default_factory=lambda: _env("RING_SIGNATURE_HEADER", "X-Signature"))
    ring_client_id: str = field(default_factory=lambda: _env("RING_CLIENT_ID"))
    ring_client_secret: str = field(default_factory=lambda: _env("RING_CLIENT_SECRET"))
    ring_account_token: str = field(default_factory=lambda: _env("RING_ACCOUNT_TOKEN"))
    ring_api_base_url: str = field(
        default_factory=lambda: _env("RING_API_BASE_URL", "https://api.amazonvision.com")
    )

    aws_region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))
    bedrock_model_id: str = field(default_factory=lambda: _env("BEDROCK_MODEL_ID"))
    eventbridge_bus_name: str = field(default_factory=lambda: _env("EVENTBRIDGE_BUS_NAME"))
    llm_timeout_seconds: int = field(default_factory=lambda: _int("LLM_TIMEOUT_SECONDS", 5))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL"))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    google_api_key: str = field(default_factory=lambda: _env("GOOGLE_API_KEY"))
    ollama_base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434"))

    mcp_http_token: str = field(default_factory=lambda: _env("MCP_HTTP_TOKEN"))
    mcp_origin: str = field(default_factory=lambda: _env("MCP_ORIGIN"))
    oauth_issuer: str = field(default_factory=lambda: _env("OAUTH_ISSUER"))
    oauth_jwks_url: str = field(default_factory=lambda: _env("OAUTH_JWKS_URL"))
    oauth_audience: str = field(default_factory=lambda: _env("OAUTH_AUDIENCE"))
    mcp_resource: str = field(default_factory=lambda: _env("MCP_RESOURCE"))
    oauth_require_resource: bool = field(default_factory=lambda: _flag("OAUTH_REQUIRE_RESOURCE", False))
    cf_access_jwt_enabled: bool = field(default_factory=lambda: _flag("CF_ACCESS_JWT_ENABLED", False))
    mcp_401_www_authenticate: bool = field(
        default_factory=lambda: _flag("MCP_401_WWW_AUTHENTICATE", True)
    )
    calendar_mcp_url: str = field(default_factory=lambda: _env("CALENDAR_MCP_URL"))
    calendar_mcp_token: str = field(default_factory=lambda: _env("CALENDAR_MCP_TOKEN"))
    context_budget_ms: int = field(default_factory=lambda: _int("CONTEXT_BUDGET_MS", 200))
    enrich_budget_ms: int = field(default_factory=lambda: _int("ENRICH_BUDGET_MS", 2000))
    quiet_hours_start: str = field(default_factory=lambda: _env("QUIET_HOURS_START"))
    quiet_hours_end: str = field(default_factory=lambda: _env("QUIET_HOURS_END"))
    api_token: str = field(default_factory=lambda: _env("API_TOKEN"))
    api_auth_disabled: bool = field(default_factory=_api_auth_disabled)
    purge_interval_s: int = field(default_factory=lambda: _int("PURGE_INTERVAL_S", 86400))
    port: int = field(default_factory=lambda: _int("PORT", 8080))

    demo_token: str = field(default_factory=lambda: _env("DEMO_TOKEN"))
    rate_limit_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_PER_MINUTE", 30))
    debounce_seconds: int = field(default_factory=lambda: _int("DEBOUNCE_SECONDS", 10))
    event_ttl_days: int = field(default_factory=lambda: _int("EVENT_TTL_DAYS", 30))
    announce_enabled: bool = field(default_factory=lambda: _flag("ANNOUNCE_ENABLED", False))


    app_env: str = field(default_factory=lambda: _env("APP_ENV", "development").lower())
    forwarded_allow_ips: str = field(default_factory=lambda: _env("FORWARDED_ALLOW_IPS", ""))
    notifier_provider: str = field(default_factory=lambda: _env("NOTIFIER_PROVIDER", "log").lower())
    sns_topic_arn: str = field(default_factory=lambda: _env("SNS_TOPIC_ARN"))
    ses_sender_email: str = field(default_factory=lambda: _env("SES_SENDER_EMAIL"))
    oauth_scope_prefix: str = field(default_factory=lambda: _env("OAUTH_SCOPE_PREFIX", ""))
    oauth_client_ids: str = field(default_factory=lambda: _env("OAUTH_CLIENT_IDS", ""))


settings = Settings()