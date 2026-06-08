"""Allowed repair workflow transitions (Phase 5 — soft FSM)."""

from __future__ import annotations

from django.core.exceptions import ValidationError

from operations.models import JobCard


def allowed_next_statuses(current: str) -> frozenset[str]:
    """Return status values that may follow ``current``."""
    graph: dict[str, frozenset[str]] = {
        JobCard.STATUS_INTAKE: frozenset(
            {JobCard.STATUS_DIAGNOSING, JobCard.STATUS_CANCELLED}
        ),
        JobCard.STATUS_DIAGNOSING: frozenset(
            {
                JobCard.STATUS_AWAITING_PARTS,
                JobCard.STATUS_IN_REPAIR,
                JobCard.STATUS_CANCELLED,
            }
        ),
        JobCard.STATUS_AWAITING_PARTS: frozenset(
            {
                JobCard.STATUS_IN_REPAIR,
                JobCard.STATUS_DIAGNOSING,
                JobCard.STATUS_CANCELLED,
            }
        ),
        JobCard.STATUS_IN_REPAIR: frozenset(
            {
                JobCard.STATUS_QA,
                JobCard.STATUS_AWAITING_PARTS,
                JobCard.STATUS_CANCELLED,
            }
        ),
        JobCard.STATUS_QA: frozenset(
            {
                JobCard.STATUS_READY,
                JobCard.STATUS_IN_REPAIR,
                JobCard.STATUS_CANCELLED,
            }
        ),
        JobCard.STATUS_READY: frozenset(
            {
                JobCard.STATUS_COMPLETED,
                JobCard.STATUS_QA,
                JobCard.STATUS_CANCELLED,
            }
        ),
        JobCard.STATUS_COMPLETED: frozenset(),
        JobCard.STATUS_CANCELLED: frozenset(),
    }
    return graph.get(current, frozenset())


def validate_job_status_transition(*, previous: str | None, new: str) -> None:
    """Raise ValidationError if ``new`` is not allowed after ``previous``."""
    if previous is None or previous == new:
        return
    allowed = allowed_next_statuses(previous)
    if new not in allowed:
        raise ValidationError(
            {
                "status": (
                    f"Cannot move from “{dict(JobCard.STATUS_CHOICES).get(previous, previous)}” "
                    f"to “{dict(JobCard.STATUS_CHOICES).get(new, new)}”. "
                    "Use the next step in the repair workflow, or cancel the job."
                )
            }
        )
