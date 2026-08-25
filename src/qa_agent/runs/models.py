from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from qa_agent.database import Base
from qa_agent.failures import FailureCategory


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        return value.astimezone(UTC) if value else None

    def process_result_value(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ERROR = "error"
    CANCELLED = "cancelled"


class RunEventKind(StrEnum):
    STATUS = "status"
    ACTION = "action"
    ASSERTION = "assertion"


run_status_type = Enum(
    RunStatus,
    name="run_status",
    native_enum=False,
    values_callable=lambda statuses: [status.value for status in statuses],
    validate_strings=True,
)
run_event_kind_type = Enum(
    RunEventKind,
    name="run_event_kind",
    native_enum=False,
    values_callable=lambda kinds: [kind.value for kind in kinds],
    validate_strings=True,
)
failure_category_type = Enum(
    FailureCategory,
    name="failure_category",
    native_enum=False,
    values_callable=lambda categories: [category.value for category in categories],
    validate_strings=True,
)
timestamp_type = UTCDateTime()


class TaskRunRecord(Base):
    __tablename__ = "task_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', "
            "'blocked', 'error', 'cancelled')",
            name="run_status",
        ),
        Index("ix_task_runs_created", "created_at", "id"),
        Index("ix_task_runs_status_created", "status", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(60))
    start_url: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[RunStatus] = mapped_column(run_status_type)
    created_at: Mapped[datetime] = mapped_column(timestamp_type, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(timestamp_type)
    finished_at: Mapped[datetime | None] = mapped_column(timestamp_type)

    final_url: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None]
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    failure_category: Mapped[FailureCategory | None] = mapped_column(
        failure_category_type
    )
    artifact_directory: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    model_config_version: Mapped[str | None] = mapped_column(String(32))

    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cache_read_tokens: Mapped[int | None]
    request_count: Mapped[int | None]
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))


class RunEventRecord(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('status', 'action', 'assertion')",
            name="run_event_kind",
        ),
        CheckConstraint(
            "status IS NULL OR status IN ('queued', 'running', 'passed', "
            "'failed', 'blocked', 'error', 'cancelled')",
            name="run_status",
        ),
        Index("ix_run_events_run_id_id", "run_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id", ondelete="CASCADE"))
    kind: Mapped[RunEventKind] = mapped_column(run_event_kind_type)
    created_at: Mapped[datetime] = mapped_column(timestamp_type, default=utc_now)

    status: Mapped[RunStatus | None] = mapped_column(run_status_type)
    action: Mapped[str | None] = mapped_column(String(32))
    element: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool | None] = mapped_column(Boolean)
    message: Mapped[str | None] = mapped_column(Text)
