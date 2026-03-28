"""Role-based access control models.

Defines the RBAC layer: roles, permissions, role-permission mappings,
and per-person role assignments scoped to organisatie-eenheden.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class Role(Base):
    """Predefined role definition (seeded, not user-created)."""

    __tablename__ = "role"

    id: Mapped[str] = mapped_column(primary_key=True)
    naam: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(
        nullable=False,
        comment="system|ministry|unit",
    )
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Higher = more powerful, for hierarchy comparison",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
    )


class Permission(Base):
    """Permission string definition (seeded reference table)."""

    __tablename__ = "permission"

    id: Mapped[str] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RolePermission(Base):
    """Many-to-many link between roles and permissions (seeded)."""

    __tablename__ = "role_permission"

    role_id: Mapped[str] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[str] = mapped_column(
        ForeignKey("permission.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship("Permission")


class PersonRole(Base):
    """Assigns a role to a person, optionally scoped to an organisatie-eenheid."""

    __tablename__ = "person_role"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "role_id",
            "organisatie_eenheid_id",
            name="uq_person_role",
        ),
        CheckConstraint(
            "(role_id IN ('super_admin', 'platform_admin')"
            " AND organisatie_eenheid_id IS NULL)"
            " OR "
            "(role_id NOT IN ('super_admin', 'platform_admin')"
            " AND organisatie_eenheid_id IS NOT NULL)",
            name="ck_person_role_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"),
        nullable=False,
    )
    organisatie_eenheid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    start_datum: Mapped[date] = mapped_column(Date, nullable=False)
    eind_datum: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    person: Mapped["Person"] = relationship(  # noqa: F821
        "Person", foreign_keys=[person_id]
    )
    role: Mapped["Role"] = relationship("Role")
    organisatie_eenheid: Mapped["OrganisatieEenheid"] = relationship(  # noqa: F821
        "OrganisatieEenheid"
    )
    granted_by: Mapped["Person"] = relationship(  # noqa: F821
        "Person", foreign_keys=[granted_by_id]
    )
