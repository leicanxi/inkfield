"""create identity, preference and idempotency tables"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_0002"
down_revision: str | None = "20260716_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("display_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("locale", sa.String(20), nullable=False, server_default="zh-CN"),
        sa.Column("auth_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleting', 'deleted')",
            name="status_values",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_status_updated_at", "users", ["status", "updated_at"])

    op.create_table(
        "user_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_subject", sa.String(200), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_identities_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_user_identities"),
        sa.UniqueConstraint(
            "provider", "provider_subject", name="uq_user_identity_provider_subject"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_user_identity_id_user"),
    )

    op.create_table(
        "user_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("device_label", sa.String(100)),
        sa.Column("fingerprint_hash", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "platform IN ('wechat_mini', 'web', 'ios', 'android')",
            name="platform_values",
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="status_values"),
        sa.CheckConstraint(
            "fingerprint_hash IS NULL OR length(fingerprint_hash) = 64",
            name="fingerprint_hash_length",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_devices_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_user_devices"),
        sa.UniqueConstraint("id", "user_id", name="uq_user_devices_id_user"),
    )
    op.create_index(
        "uq_user_devices_user_fingerprint_active",
        "user_devices",
        ["user_id", "fingerprint_hash"],
        unique=True,
        postgresql_where=sa.text("fingerprint_hash IS NOT NULL"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auth_version_snapshot", sa.BigInteger(), nullable=False),
        sa.Column("session_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.String(30)),
        sa.CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="status_values",
        ),
        sa.CheckConstraint(
            "revoke_reason IS NULL OR revoke_reason IN "
            "('logout', 'device_revoked', 'token_reuse', 'user_disabled', 'global_logout')",
            name="revoke_reason_values",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_sessions_user_id_users"),
        sa.ForeignKeyConstraint(
            ["identity_id", "user_id"],
            ["user_identities.id", "user_identities.user_id"],
            name="fk_auth_sessions_identity_user",
        ),
        sa.ForeignKeyConstraint(
            ["device_id", "user_id"],
            ["user_devices.id", "user_devices.user_id"],
            name="fk_auth_sessions_device_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("id", "user_id", name="uq_auth_sessions_id_user"),
    )
    op.create_index("ix_auth_sessions_user_status", "auth_sessions", ["user_id", "status"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("parent_token_id", postgresql.UUID(as_uuid=True)),
        sa.Column("replaced_by_token_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('active', 'rotated', 'revoked', 'reused', 'expired')",
            name="status_values",
        ),
        sa.CheckConstraint("length(token_hash) = 64", name="token_hash_length"),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["auth_sessions.id", "auth_sessions.user_id"],
            name="fk_refresh_tokens_session_user",
        ),
        sa.ForeignKeyConstraint(
            ["parent_token_id"], ["refresh_tokens.id"], name="fk_refresh_tokens_parent"
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_token_id"], ["refresh_tokens.id"], name="fk_refresh_tokens_replacement"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index(
        "uq_refresh_tokens_one_active_per_session",
        "refresh_tokens",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weekly_capacity_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("utilization_ratio", sa.Numeric(4, 3), nullable=False, server_default="0.850"),
        sa.Column("preferred_task_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_task_minutes", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("available_weekdays", sa.SmallInteger(), nullable=False, server_default="127"),
        sa.Column(
            "stable_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("preference_revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("weekly_capacity_minutes >= 0", name="weekly_capacity_nonnegative"),
        sa.CheckConstraint(
            "utilization_ratio >= 0 AND utilization_ratio <= 1",
            name="utilization_ratio_range",
        ),
        sa.CheckConstraint("preferred_task_minutes > 0", name="preferred_task_positive"),
        sa.CheckConstraint(
            "max_task_minutes >= preferred_task_minutes",
            name="max_task_not_smaller",
        ),
        sa.CheckConstraint(
            "available_weekdays >= 0 AND available_weekdays <= 127",
            name="available_weekdays_mask",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_preferences_user_id_users"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_preferences"),
    )

    op.create_table(
        "api_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_method", sa.String(10), nullable=False),
        sa.Column("request_path", sa.String(500), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("resource_type", sa.String(80)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'failed')",
            name="status_values",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name="request_hash_length",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_api_idempotency_records_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_idempotency_records"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_api_idempotency_user_key"),
    )
    op.create_index("ix_api_idempotency_expiry", "api_idempotency_records", ["expires_at"])


def downgrade() -> None:
    op.drop_table("api_idempotency_records")
    op.drop_table("user_preferences")
    op.drop_table("refresh_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("user_devices")
    op.drop_table("user_identities")
    op.drop_table("users")
