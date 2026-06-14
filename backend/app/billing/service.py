"""Billing service — monthly free-quota metering and per-page overage charging.

The pure helpers in this module (``current_year_month``, ``compute_chargeable_pages``,
``chargeable_cost_vnd``) have no I/O so the quota boundaries can be unit-tested in
isolation. DB-backed charging is layered on top in later tasks.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from sqlmodel import Session

from app.billing.constants import (
    FREE_PAGES_PER_MONTH,
    PRICE_PER_PAGE_VND,
    VN_TIMEZONE,
)
from app.billing.crud import (
    get_monthly_usage,
    get_or_create_monthly_usage,
    increment_monthly_usage,
)
from app.files.models import FileJob
from app.topup import crud as topup_crud
from app.topup.models import TopupStatus, TopupTransaction, TopupType
from app.users.models import User
from app.utils import get_datetime_utc


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


def charge_for_job(
    session: Session, *, user: User, file_job: FileJob
) -> TopupTransaction | None:
    """Meter and charge a completed OCR job exactly once.

    Applies the monthly free quota first, then bills any overage to the user's
    prepaid VND balance — charging only what the balance can cover (results are
    still delivered on a shortfall). Increments the month's ``pages_used`` by the
    job's page count and stamps ``billed_at`` as the idempotency guard.

    Returns the DEBIT ``TopupTransaction`` when a charge was made, or ``None`` when
    the job was free, had no pages, or was already billed.
    """
    if file_job.billed_at is not None:
        return None

    pages = file_job.total_pages or 0
    if pages <= 0:
        return None

    usage = get_or_create_monthly_usage(
        session, user_id=user.id, year_month=current_year_month()
    )
    chargeable = compute_chargeable_pages(usage.pages_used, pages)
    cost = chargeable_cost_vnd(chargeable)

    txn: TopupTransaction | None = None
    if cost > 0:
        balance = topup_crud.get_or_create_balance(session, user.id)
        amount = min(float(cost), balance.balance)
        if amount > 0:
            txn = topup_crud.create_transaction(
                session,
                user_id=user.id,
                amount=amount,
                type=TopupType.DEBIT,
                txn_ref=str(file_job.id),
                note=f"OCR job {file_job.id}: {pages} pages, {chargeable} chargeable",
                status=TopupStatus.SUCCESS,
            )
            topup_crud.apply_balance_change(session, balance, amount, TopupType.DEBIT)

    increment_monthly_usage(session, usage, pages)
    file_job.billed_at = get_datetime_utc()
    session.add(file_job)
    session.commit()
    if txn is not None:
        session.refresh(txn)
    return txn


def estimate_pdf_pages(data: bytes) -> int | None:
    """Best-effort PDF page count, or ``None`` when the bytes aren't a readable PDF."""
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return None


def preflight_overage_block(
    session: Session, *, user: User, file_bytes: bytes, content_type: str
) -> dict[str, Any] | None:
    """Pre-flight affordability check run before the file is sent to the OCR API.

    Estimates the PDF's pages and, if the projected overage cost exceeds the user's
    prepaid balance, returns a 402 detail payload so the upload can be rejected before
    incurring external OCR cost. Returns ``None`` (allow) for non-PDF/uncountable
    uploads or when the job fits within the free quota + balance.
    """
    if "pdf" not in (content_type or "").lower():
        return None
    pages = estimate_pdf_pages(file_bytes)
    if pages is None:
        return None

    usage = get_monthly_usage(session, user_id=user.id, year_month=current_year_month())
    pages_used = usage.pages_used if usage else 0
    cost = chargeable_cost_vnd(compute_chargeable_pages(pages_used, pages))
    if cost == 0:
        return None

    balance = topup_crud.get_or_create_balance(session, user.id)
    if cost > balance.balance:
        return {
            "message": "Insufficient balance for the estimated overage. Please top up.",
            "estimated_pages": pages,
            "estimated_cost_vnd": cost,
            "balance_vnd": balance.balance,
        }
    return None
