"""Reusable SQLAlchemy column types for backend models."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

JsonDict = JSON().with_variant(JSONB, "postgresql")
JsonList = JSON().with_variant(JSONB, "postgresql")
