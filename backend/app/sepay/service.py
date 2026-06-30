"""SePay service — business logic for the bank-transfer webhook flow.

SePay watches a linked bank account and fires a webhook when money arrives. We
generate the VietQR client-side (qr.sepay.vn), persist a PENDING top-up
transaction keyed by a unique content code, and credit the user's balance when
the matching webhook is delivered. Reuses the provider-agnostic top-up core in
``app.topup``.
"""

from __future__ import annotations

import re
import time
import uuid
from urllib.parse import urlencode

from sqlmodel import Session

from app.core.config import settings
from app.sepay.schemas import (
    CreateSepayPaymentResponse,
    SepayWebhookPayload,
    SepayWebhookResponse,
)
from app.topup import crud
from app.topup.constants import (
    ALLOWED_AMOUNTS,
    bonus_for_amount,
    bonus_percent_for_amount,
)
from app.topup.models import TopupStatus, TopupType

SEPAY_QR_BASE = "https://qr.sepay.vn/img"


def build_qr_url(amount: int, content: str) -> str:
    """Build a qr.sepay.vn VietQR image URL pre-filled for this top-up."""
    query = urlencode(
        {
            "acc": settings.SEPAY_BANK_ACCOUNT or "",
            "bank": settings.SEPAY_BANK_CODE or "",
            "amount": amount,
            "des": content,
        }
    )
    return f"{SEPAY_QR_BASE}?{query}"


def create_sepay_payment(
    session: Session,
    *,
    user_id: uuid.UUID,
    user_email: str,
    amount: int,
) -> CreateSepayPaymentResponse:
    """Persist a PENDING top-up transaction and return the QR + bank details.

    The content code (``txn_ref``) is alphanumeric so it survives bank content
    normalisation, and unique so the webhook can resolve the user later.
    """
    txn_ref = f"{settings.SEPAY_CONTENT_PREFIX}{int(time.time() * 1000)}"
    crud.create_transaction(
        session,
        user_id=user_id,
        amount=float(amount),
        type=TopupType.CREDIT,
        txn_ref=txn_ref,
        note=f"SePay nap tien tai khoan {user_email}",
        status=TopupStatus.PENDING,
    )
    session.commit()

    return CreateSepayPaymentResponse(
        qr_url=build_qr_url(amount, txn_ref),
        txn_ref=txn_ref,
        amount=amount,
        account=settings.SEPAY_BANK_ACCOUNT or "",
        bank=settings.SEPAY_BANK_CODE or "",
        content=txn_ref,
    )


def is_valid_amount(amount: int) -> bool:
    return amount in ALLOWED_AMOUNTS


def extract_payment_code(payload: SepayWebhookPayload) -> str | None:
    """Recover our content code from a webhook payload.

    Prefer the ``code`` field SePay auto-extracts (when a prefix pattern is
    configured in the dashboard); otherwise scan the raw ``content`` for our
    ``<PREFIX><digits>`` code.
    """
    prefix = settings.SEPAY_CONTENT_PREFIX.upper()
    if payload.code and payload.code.upper().startswith(prefix):
        return payload.code.upper()
    match = re.search(rf"{re.escape(prefix)}\d+", payload.content.upper())
    return match.group(0) if match else None


def handle_webhook(
    session: Session, payload: SepayWebhookPayload
) -> SepayWebhookResponse:
    """Process a SePay webhook delivery and credit the balance on a match.

    Returns ``success=True`` for anything we have safely acknowledged (including
    foreign transfers and duplicate deliveries) so SePay stops retrying;
    ``success=False`` only on a transient DB error so SePay retries.

    Idempotency rides on the existing one-``txn_ref``-per-transaction +
    ``status == SUCCESS`` guard (mirrors ``topup.service.handle_ipn``).
    """
    from app.backend_pre_start import logger

    logger.info("Received SePay webhook: id=%s content=%s", payload.id, payload.content)

    # Only incoming transfers add balance.
    if payload.transferType != "in":
        return SepayWebhookResponse(success=True)

    code = extract_payment_code(payload)
    if code is None:
        logger.info("SePay webhook: no matching code in content=%r", payload.content)
        return SepayWebhookResponse(success=True)

    txn = crud.get_transaction_by_txn_ref(session, code)
    if txn is None:
        logger.warning("SePay webhook: no transaction for code=%s", code)
        return SepayWebhookResponse(success=True)

    # Duplicate delivery — already credited.
    if txn.status == TopupStatus.SUCCESS:
        return SepayWebhookResponse(success=True)

    # Accept overpayment, reject underpayment (SePay best practice).
    if payload.transferAmount < txn.amount:
        logger.warning(
            "SePay webhook: underpaid code=%s expected=%s got=%s",
            code,
            txn.amount,
            payload.transferAmount,
        )
        return SepayWebhookResponse(success=True)

    try:
        balance = crud.get_or_create_balance(session, txn.user_id)
        txn.note = (
            f"SePay ref={payload.referenceCode} id={payload.id}"
            if payload.referenceCode
            else f"SePay id={payload.id}"
        )
        crud.mark_transaction(session, txn, TopupStatus.SUCCESS)
        crud.apply_balance_change(session, balance, txn.amount, TopupType.CREDIT)

        # Credit the loyalty bonus (if any) as a separate transaction so it
        # shows up distinctly in the user's history. A suffixed txn_ref keeps
        # the webhook's code lookup pointing at the original top-up.
        bonus = bonus_for_amount(int(txn.amount))
        if bonus > 0:
            percent = bonus_percent_for_amount(int(txn.amount))
            crud.create_transaction(
                session,
                user_id=txn.user_id,
                amount=float(bonus),
                type=TopupType.CREDIT,
                txn_ref=f"{code}-BONUS",
                note=f"SePay bonus {percent}% for top-up {code}",
                status=TopupStatus.SUCCESS,
            )
            crud.apply_balance_change(session, balance, float(bonus), TopupType.CREDIT)

        session.commit()
        logger.info(
            "SePay webhook: credited %s (+%s bonus) VND to user %s (code=%s)",
            txn.amount,
            bonus,
            txn.user_id,
            code,
        )
    except Exception as exc:  # noqa: BLE001 — return failure so SePay retries
        session.rollback()
        logger.error("SePay webhook: failed to credit code=%s: %s", code, exc)
        return SepayWebhookResponse(success=False)

    return SepayWebhookResponse(success=True)
