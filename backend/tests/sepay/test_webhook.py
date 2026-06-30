import uuid

from sqlmodel import Session

from app.sepay.schemas import SepayWebhookPayload
from app.sepay.service import create_sepay_payment, handle_webhook
from app.topup.crud import get_or_create_balance, get_transaction_by_txn_ref
from app.topup.models import TopupStatus
from app.users.models import User
from app.users.schemas import UserCreate
from app.users.service import create_user
from tests.utils.utils import random_email, random_lower_string


def _make_user(db: Session) -> User:
    return create_user(
        session=db,
        user_create=UserCreate(email=random_email(), password=random_lower_string()),
    )


def _pending_topup(db: Session, user_id: uuid.UUID, amount: int) -> str:
    resp = create_sepay_payment(
        db, user_id=user_id, user_email="x@example.com", amount=amount
    )
    return resp.txn_ref


def _payload(
    code: str, amount: float, *, transfer_type: str = "in"
) -> SepayWebhookPayload:
    return SepayWebhookPayload(
        id=int(uuid.uuid4().int % 1_000_000_000),
        content=f"chuyen tien {code}",
        transferType=transfer_type,
        transferAmount=amount,
        referenceCode="REF123",
    )


def test_webhook_credits_balance_on_match(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 50_000)

    res = handle_webhook(db, _payload(code, 50_000))

    assert res.success is True
    assert get_transaction_by_txn_ref(db, code).status == TopupStatus.SUCCESS
    assert get_or_create_balance(db, user.id).balance == start + 50_000


def test_webhook_credits_bonus_for_large_topup(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 1_000_000)

    res = handle_webhook(db, _payload(code, 1_000_000))

    assert res.success is True
    # 1,000,000 top-up earns a 6% bonus -> 60,000 extra credited.
    assert get_or_create_balance(db, user.id).balance == start + 1_060_000
    bonus_txn = get_transaction_by_txn_ref(db, f"{code}-BONUS")
    assert bonus_txn is not None
    assert bonus_txn.amount == 60_000
    assert bonus_txn.status == TopupStatus.SUCCESS


def test_webhook_bonus_credited_only_once(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 1_000_000)

    handle_webhook(db, _payload(code, 1_000_000))
    res = handle_webhook(db, _payload(code, 1_000_000))

    assert res.success is True
    # Duplicate delivery must not double the bonus.
    assert get_or_create_balance(db, user.id).balance == start + 1_060_000


def test_webhook_is_idempotent(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 50_000)

    handle_webhook(db, _payload(code, 50_000))
    res = handle_webhook(db, _payload(code, 50_000))

    assert res.success is True
    # Only credited once despite the duplicate delivery.
    assert get_or_create_balance(db, user.id).balance == start + 50_000


def test_webhook_uses_code_field_when_present(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 20_000)

    payload = SepayWebhookPayload(
        id=777,
        code=code,
        content="unrelated note",
        transferType="in",
        transferAmount=20_000,
    )
    res = handle_webhook(db, payload)

    assert res.success is True
    assert get_or_create_balance(db, user.id).balance == start + 20_000


def test_webhook_underpayment_does_not_credit(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 100_000)

    res = handle_webhook(db, _payload(code, 50_000))

    assert res.success is True  # acked so SePay stops retrying
    assert get_transaction_by_txn_ref(db, code).status == TopupStatus.PENDING
    assert get_or_create_balance(db, user.id).balance == start


def test_webhook_overpayment_credits(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 50_000)

    res = handle_webhook(db, _payload(code, 60_000))

    assert res.success is True
    assert get_transaction_by_txn_ref(db, code).status == TopupStatus.SUCCESS
    assert get_or_create_balance(db, user.id).balance == start + 50_000


def test_webhook_unknown_code_is_acked(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance

    res = handle_webhook(db, _payload("NAP9999999999999", 50_000))

    assert res.success is True
    assert get_or_create_balance(db, user.id).balance == start


def test_webhook_outgoing_transfer_ignored(db: Session) -> None:
    user = _make_user(db)
    start = get_or_create_balance(db, user.id).balance
    code = _pending_topup(db, user.id, 50_000)

    res = handle_webhook(db, _payload(code, 50_000, transfer_type="out"))

    assert res.success is True
    assert get_transaction_by_txn_ref(db, code).status == TopupStatus.PENDING
    assert get_or_create_balance(db, user.id).balance == start
