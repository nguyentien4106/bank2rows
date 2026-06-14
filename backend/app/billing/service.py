"""Billing service — monthly free-quota metering and per-page overage charging.

The pure helpers in this module (``current_year_month``, ``compute_chargeable_pages``,
``chargeable_cost_vnd``) have no I/O so the quota boundaries can be unit-tested in
isolation. DB-backed charging is layered on top in later tasks.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.billing.constants import (
    FREE_PAGES_PER_MONTH,
    PRICE_PER_PAGE_VND,
    VN_TIMEZONE,
)


def current_year_month() -> int:
    """Return the current calendar month as ``YYYYMM`` in the VN timezone."""
    now = datetime.now(ZoneInfo(VN_TIMEZONE))
    return now.year * 100 + now.month


def compute_chargeable_pages(pages_used_this_month: int, job_pages: int) -> int:
    """Pages of *job_pages* that fall beyond the monthly free quota.

    Free pages are consumed first within the month, so only the portion of *this*
    job left after the remaining free allowance is chargeable. ``pages_used_this_month``
    already accounts for any earlier (possibly billed) pages, so we charge against the
    *remaining* free pages rather than re-applying the whole quota — this keeps each
    page billed exactly once (sum of per-job charges == ``max(0, total - free)``).
    """
    free_remaining = max(0, FREE_PAGES_PER_MONTH - pages_used_this_month)
    return max(0, job_pages - free_remaining)


def chargeable_cost_vnd(chargeable_pages: int) -> int:
    """Cost in VND for *chargeable_pages* of overage."""
    return chargeable_pages * PRICE_PER_PAGE_VND
