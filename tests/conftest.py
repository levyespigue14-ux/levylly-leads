import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client():
    """API com banco limpo a cada teste: SQLite em memória, ou o PostgreSQL de TEST_DATABASE_URL."""
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def lead(client):
    r = client.post("/leads", json={
        "nome": "Doceria Teste", "nicho": "confeitaria", "cidade": "São Paulo",
        "whatsapp": "(11) 91234-5678", "instagram": "@doceria", "avaliacao": 4.9, "num_avaliacoes": 300,
    })
    assert r.status_code == 201, r.text
    return r.json()
