"""Shared model metadata and per-application database resources."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_database(url: str):
    options = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite:") else {}
    engine = create_engine(url, **options)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
