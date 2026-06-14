"""CRUD helpers for monthly usage rows."""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.billing.models import MonthlyUsage
from app.utils import get_datetime_utc


def get_monthly_usage(
    session: Session, *, user_id: uuid.UUID, year_month: int
) -> MonthlyUsage | None:
    """Return the usage row for ``(user_id, year_month)`` without creating one."""
    return session.exec(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.year_month == year_month,
        )
    ).first()


def get_or_create_monthly_usage(
    session: Session, *, user_id: uuid.UUID, year_month: int
) -> MonthlyUsage:
    """Return the usage row for ``(user_id, year_month)``, creating it if absent."""
    usage = session.exec(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.year_month == year_month,
        )
    ).first()
    if usage is None:
        usage = MonthlyUsage(user_id=user_id, year_month=year_month, pages_used=0)
        session.add(usage)
        session.flush()
    return usage


def increment_monthly_usage(
    session: Session, usage: MonthlyUsage, pages: int
) -> MonthlyUsage:
    """Add *pages* to the running monthly total."""
    usage.pages_used += pages
    usage.updated_at = get_datetime_utc()
    session.add(usage)
    session.flush()
    return usage
