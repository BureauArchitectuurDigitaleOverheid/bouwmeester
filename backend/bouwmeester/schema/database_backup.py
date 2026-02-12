"""Pydantic schemas for database backup/restore operations."""

from pydantic import BaseModel


class DatabaseBackupInfo(BaseModel):
    exported_at: str
    alembic_revision: str
    format_version: int
    encrypted: bool


class DatabaseRestoreResult(BaseModel):
    success: bool
    tables_restored: int
    alembic_revision_from: str
    alembic_revision_to: str
    migrations_applied: int
    message: str


class DatabaseResetRequest(BaseModel):
    confirm: str


class DatabaseResetResult(BaseModel):
    success: bool
    tables_cleared: int
    admin_persons_created: int
    message: str
