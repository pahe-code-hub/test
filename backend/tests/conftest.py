import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import models  # noqa: F401 - registers ORM classes on Base.metadata
from app.main import app


@pytest.fixture()
def test_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(test_engine):
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


VALID_INTAKE = {
    "goal": "Zeit sparen bei der Angebotserstellung",
    "problem": "Angebote werden manuell in Word erstellt und dauern zu lange",
    "users_structure": "kleines Vertriebsteam, 5 Personen",
    "interface_output": "Web-App",
    "constraints": "lokal, keine Cloud-Pflicht, DSGVO-konform",
    "core_features": "Vorlagenverwaltung, PDF-Export, Kundendaten-Import",
}
