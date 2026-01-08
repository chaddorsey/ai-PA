"""Initial schema for pa_web tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_NAME = "pa_web"


def upgrade() -> None:
    # Create schema
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")

    # Create conversations table
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        op.f("ix_conversations_session_id"),
        "conversations",
        ["session_id"],
        unique=False,
        schema=SCHEMA_NAME,
    )
    op.create_index(
        op.f("ix_conversations_created_at"),
        "conversations",
        ["created_at"],
        unique=False,
        schema=SCHEMA_NAME,
    )

    # Create routing_decisions table
    op.create_table(
        "routing_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_preview", sa.String(length=255), nullable=True),
        sa.Column("selected_agent_id", sa.String(length=255), nullable=False),
        sa.Column("routing_method", sa.String(length=50), nullable=True),
        sa.Column("routing_confidence", sa.Float(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_routing_decisions")),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        op.f("ix_routing_decisions_session_id"),
        "routing_decisions",
        ["session_id"],
        unique=False,
        schema=SCHEMA_NAME,
    )

    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("current_agent_id", sa.String(length=255), nullable=True),
        sa.Column("preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_activity", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_sessions")),
        schema=SCHEMA_NAME,
    )
    op.create_index(
        op.f("ix_sessions_last_activity"),
        "sessions",
        ["last_activity"],
        unique=False,
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    op.drop_table("sessions", schema=SCHEMA_NAME)
    op.drop_table("routing_decisions", schema=SCHEMA_NAME)
    op.drop_table("conversations", schema=SCHEMA_NAME)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME}")
