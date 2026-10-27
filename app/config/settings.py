from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

DEFAULT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database. SQLite works out of the box; use MySQL in production, e.g.
    # mysql+pymysql://user:password@localhost:3306/task_board_db
    TEAM_TASK_BOARD_SCHEMA: str = "sqlite:///./taskboard.db"
    SQL_ECHO: bool = False
    # Create tables on startup. Turn off once you manage the schema with Alembic.
    AUTO_CREATE_TABLES: bool = True

    ENVIRONMENT: str = "development"  # "production" turns on secure cookies + secret check
    SECRET_KEY: str = DEFAULT_SECRET
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 30
    EMAIL_VERIFICATION_HOURS: int = 24
    PASSWORD_RESET_MINUTES: int = 60
    INVITATION_DAYS: int = 14

    # Where the React app lives (used in links inside emails) and which origins may call the API.
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    # Email. "console" prints messages to the server log (development).
    EMAIL_BACKEND: str = "console"  # console | smtp
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    SMTP_FROM: str = "TaskBoard <no-reply@localhost>"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()

if settings.is_production and settings.SECRET_KEY == DEFAULT_SECRET:
    raise RuntimeError("Set SECRET_KEY in the environment before running in production.")


def make_engine(url: str, **kwargs) -> Engine:
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    else:
        kwargs.setdefault("pool_pre_ping", True)
        kwargs.setdefault("pool_recycle", 1800)
    built = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(built, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return built


engine = make_engine(settings.TEAM_TASK_BOARD_SCHEMA, echo=settings.SQL_ECHO)


def create_db_and_tables() -> None:
    import app.schemas.models  # noqa: F401  (registers every table on the metadata)

    SQLModel.metadata.create_all(engine)
