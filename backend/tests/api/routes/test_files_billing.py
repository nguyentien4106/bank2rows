import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlmodel import Session

from app.billing.crud import get_or_create_monthly_usage
from app.billing.service import current_year_month
from app.core.config import settings
from app.topup.crud import get_or_create_balance
from app.users.service import get_user_by_email


def _make_pdf_bytes(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _prepare_user(db: Session, balance: float, pages_used: int) -> None:
    user = get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    bal = get_or_create_balance(db, user.id)
    bal.balance = balance
    db.add(bal)
    usage = get_or_create_monthly_usage(
        db, user_id=user.id, year_month=current_year_month()
    )
    usage.pages_used = pages_used
    db.add(usage)
    db.commit()


def test_upload_blocked_when_estimate_exceeds_balance(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    # no free pages left, tiny balance; a 5-page PDF -> 5 * 500 = 2500 VND > 1000
    _prepare_user(db, balance=1000, pages_used=50)
    pdf = _make_pdf_bytes(5)

    with (
        patch("app.files.router.post_ocr_jobs") as mock_post,
        patch("app.files.router.upload_file_to_r2") as mock_r2,
    ):
        resp = client.post(
            f"{settings.API_V1_STR}/files/",
            headers=normal_user_token_headers,
            files={"file": ("stmt.pdf", pdf, "application/pdf")},
        )

    assert resp.status_code == 402
    mock_post.assert_not_called()
    mock_r2.assert_not_called()


def test_upload_proceeds_when_balance_sufficient(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    _prepare_user(db, balance=100_000, pages_used=50)
    pdf = _make_pdf_bytes(5)

    with (
        patch("app.files.router.post_ocr_jobs") as mock_post,
        patch(
            "app.files.router.upload_file_to_r2",
            return_value={"IsSuccess": True, "PresignedURL": "http://x/presigned"},
        ),
    ):
        resp = client.post(
            f"{settings.API_V1_STR}/files/",
            headers=normal_user_token_headers,
            files={"file": ("stmt.pdf", pdf, "application/pdf")},
        )

    assert resp.status_code == 200
    mock_post.assert_called_once()


def test_upload_within_free_quota_proceeds(
    client: TestClient, normal_user_token_headers: dict[str, str], db: Session
) -> None:
    # zero balance but within the free monthly quota -> must not be blocked
    _prepare_user(db, balance=0, pages_used=0)
    pdf = _make_pdf_bytes(5)

    with (
        patch("app.files.router.post_ocr_jobs") as mock_post,
        patch(
            "app.files.router.upload_file_to_r2",
            return_value={"IsSuccess": True, "PresignedURL": "http://x/presigned"},
        ),
    ):
        resp = client.post(
            f"{settings.API_V1_STR}/files/",
            headers=normal_user_token_headers,
            files={"file": ("stmt.pdf", pdf, "application/pdf")},
        )

    assert resp.status_code == 200
    mock_post.assert_called_once()
