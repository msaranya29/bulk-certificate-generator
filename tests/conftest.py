import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import config, database, main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = database.make_engine("sqlite:///:memory:")
    database.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(config, "CERTIFICATE_DIR", str(tmp_path))

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[database.get_db] = override
    # TestClient runs background tasks before returning, so jobs are done on response.
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
