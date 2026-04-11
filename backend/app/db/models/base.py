"""Shared SQLAlchemy declarative base for backend ORM models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""
