"""
Database setup. SQLite file-based DB — this is the whole point of the MVP:
no external processor, no bank partner, just a local DB simulating accounts
and a fake currency ("SIM") so the flow can be demoed end-to-end.

If a Railway volume is attached, RAILWAY_VOLUME_MOUNT_PATH is set
automatically and the DB file is written there so it survives redeploys.
Without a volume (e.g. running locally), it falls back to a file in the
working directory, same as before.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

volume_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
if volume_path:
    db_file = os.path.join(volume_path, "purpose_wallet_mvp.db")
else:
    db_file = "./purpose_wallet_mvp.db"

SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_file}"

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
