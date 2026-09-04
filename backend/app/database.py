"""
DB-Setup gemäß DATA_MODEL.md: SQLite im WAL-Modus, ein Commit pro
Agentenlauf (siehe app/models.py und app/routers/projects.py - jede
Statusänderung + Ergebnis wird in derselben Session/Transaktion
geschrieben, kein Zwischenzustand ist von außen sichtbar).
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
