import os
import logging

from typing import Generator
from urllib.parse import quote_plus
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.infra.persistence.entities.base import Base

log = logging.getLogger(__name__)


class ApplicationDatabase:
    def __init__(self) -> None:
        self._engine = create_engine(
            self.db_url,
            echo=self._db_logging,
            connect_args=self._connect_args,
        )

        self._session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            bind=self._engine,
        )

    @property
    def _db_logging(self) -> bool:
        return os.getenv("ENV", "production") == "development"

    @property
    def db_url(self) -> str:
        env = os.getenv("ENV", "production")

        if env == "development":
            db      = os.getenv("POSTGRES_DB", "cryptobot")
            host    = os.getenv("POSTGRES_HOST", "localhost")
            port    = os.getenv("POSTGRES_PORT", "5432")
            user    = os.getenv("POSTGRES_USER", "postgres")
            password = os.getenv("POSTGRES_PASSWORD", "")

            return f"postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{db}"

        # produção: Supabase via Transaction Pooler (porta 6543) ou Session Pooler (5432)
        db      = os.getenv("POSTGRES_DB", "postgres")
        host    = os.getenv("POSTGRES_HOST", "")
        port    = os.getenv("POSTGRES_PORT", "5432")
        user    = os.getenv("POSTGRES_USER", "")
        password = os.getenv("POSTGRES_PASSWORD", "")

        return f"postgresql+psycopg2://{user}:{quote_plus(password)}@{host}:{port}/{db}"

    @property
    def _connect_args(self) -> dict:
        if os.getenv("ENV", "production") == "development":
            return {}
        
        return {"sslmode": "require"}

    def create_tables(self) -> None:
        env = os.getenv("ENV", "production")

        if env != "development":
            return
        
        Base.metadata.create_all(self._engine)
        log.info("[db] Tabelas sincronizadas (development).")

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        session: Session = self._session_factory()
        
        try:
            yield session
        except Exception:
            log.exception("Session rollback devido a excecao")
            session.rollback()
            raise
        finally:
            session.close()


db = ApplicationDatabase()
