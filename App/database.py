"""
Database setup. SQLite file-based DB — this is the whole point of the MVP:
no external processor, no bank partner, just a local DB simulating accounts
and a fake currency ("SIM") so the flow can be demoed end-to-end.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "sqlite:///./purpose_wallet_mvp.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
