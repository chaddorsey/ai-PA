"""Create scheduler schema and core tables"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "001_create_scheduler_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS scheduler")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "jobs",
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("schedule_type", sa.String(length=32), nullable=False),
        sa.Column("schedule_expression", sa.JSON(), nullable=False),
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("vector_embedding", Vector(384), nullable=True),
        schema="scheduler",
    )

    op.create_index("jobs_next_run_idx", "jobs", ["next_run_at"], schema="scheduler")
    op.create_index("jobs_status_idx", "jobs", ["status"], schema="scheduler")
    op.create_index(
        "jobs_embedding_idx",
        "jobs",
        ["vector_embedding"],
        schema="scheduler",
        postgresql_using="ivfflat",
        postgresql_ops={"vector_embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "job_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meta_key", sa.String(length=128), nullable=False),
        sa.Column("meta_value", sa.JSON(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["scheduler.jobs.job_id"], ondelete="CASCADE"),
        schema="scheduler",
    )

    op.create_index("job_metadata_job_idx", "job_metadata", ["job_id"], schema="scheduler")
    op.create_index(
        "job_metadata_embedding_idx",
        "job_metadata",
        ["embedding"],
        schema="scheduler",
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "actions",
        sa.Column("action_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("allow_list_tag", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["scheduler.jobs.job_id"], ondelete="CASCADE"),
        schema="scheduler",
    )

    op.create_index("actions_job_idx", "actions", ["job_id"], schema="scheduler")

    op.create_table(
        "executions",
        sa.Column("execution_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("log_summary", sa.Text(), nullable=True),
        sa.Column("result_reference", sa.String(length=255), nullable=True),
        sa.Column("vector_embedding", Vector(384), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["scheduler.jobs.job_id"], ondelete="CASCADE"),
        schema="scheduler",
    )

    op.create_index(
        "executions_job_scheduled_idx",
        "executions",
        ["job_id", sa.text("scheduled_at DESC")],
        schema="scheduler",
    )
    op.create_index(
        "executions_embedding_idx",
        "executions",
        ["vector_embedding"],
        schema="scheduler",
        postgresql_using="ivfflat",
        postgresql_ops={"vector_embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "execution_outputs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("execution_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output_type", sa.String(length=32), nullable=False),
        sa.Column("output_data", sa.JSON(), nullable=False),
        sa.Column("artifact_uri", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["execution_id"], ["scheduler.executions.execution_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id"], ["scheduler.actions.action_id"], ondelete="CASCADE"),
        schema="scheduler",
    )

    op.create_table(
        "callbacks",
        sa.Column("callback_id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("callback_url", sa.Text(), nullable=False),
        sa.Column("secret_token", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["scheduler.jobs.job_id"], ondelete="CASCADE"),
        schema="scheduler",
    )

    op.create_table(
        "audit_log",
        sa.Column("audit_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("details", sa.JSON(), nullable=False),
        schema="scheduler",
    )

    op.create_table(
        "distributed_lock",
        sa.Column("lock_name", sa.String(length=128), primary_key=True),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="scheduler",
    )


def downgrade() -> None:
    op.drop_table("distributed_lock", schema="scheduler")
    op.drop_table("audit_log", schema="scheduler")
    op.drop_table("callbacks", schema="scheduler")
    op.drop_table("execution_outputs", schema="scheduler")
    op.drop_index("executions_embedding_idx", table_name="executions", schema="scheduler")
    op.drop_index("executions_job_scheduled_idx", table_name="executions", schema="scheduler")
    op.drop_table("executions", schema="scheduler")
    op.drop_index("actions_job_idx", table_name="actions", schema="scheduler")
    op.drop_table("actions", schema="scheduler")
    op.drop_index("job_metadata_embedding_idx", table_name="job_metadata", schema="scheduler")
    op.drop_index("job_metadata_job_idx", table_name="job_metadata", schema="scheduler")
    op.drop_table("job_metadata", schema="scheduler")
    op.drop_index("jobs_embedding_idx", table_name="jobs", schema="scheduler")
    op.drop_index("jobs_status_idx", table_name="jobs", schema="scheduler")
    op.drop_index("jobs_next_run_idx", table_name="jobs", schema="scheduler")
    op.drop_table("jobs", schema="scheduler")
    op.execute("DROP SCHEMA IF EXISTS scheduler CASCADE")

