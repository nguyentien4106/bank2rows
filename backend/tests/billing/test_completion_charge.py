import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from sqlmodel import Session

import app.ocrs.service as ocr_service
from app.billing.crud import get_or_create_monthly_usage
from app.billing.service import current_year_month
from app.files.models import File, FileJob
from app.ocrs.constants import OcrJobStatus
from app.topup.crud import get_or_create_balance
from app.users.models import User
from app.users.schemas import UserCreate
from app.users.service import create_user
from tests.utils.utils import random_email, random_lower_string


def _make_user(db: Session) -> User:
    return create_user(
        session=db,
        user_create=UserCreate(email=random_email(), password=random_lower_string()),
    )


def _set_balance(db: Session, user_id: uuid.UUID, amount: float) -> None:
    balance = get_or_create_balance(db, user_id)
    balance.balance = amount
    db.add(balance)
    db.commit()


def _set_usage(db: Session, user_id: uuid.UUID, pages_used: int) -> None:
    usage = get_or_create_monthly_usage(
        db, user_id=user_id, year_month=current_year_month()
    )
    usage.pages_used = pages_used
    db.add(usage)
    db.commit()


def _make_running_job(db: Session, user_id: uuid.UUID) -> tuple[File, FileJob]:
    file = File(
        filename="stmt.pdf", content_type="application/pdf", size=10, user_id=user_id
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    job = FileJob(
        job_id=f"job-{uuid.uuid4()}", file_id=file.id, state=OcrJobStatus.RUNNING
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return file, job


def _ocr_response(state: str, total_pages: int = 0) -> dict[str, Any]:
    return {
        "code": 0,
        "data": {
            "jobId": "job-x",
            "state": state,
            "extractProgress": {
                "totalPages": total_pages,
                "extractedPages": total_pages,
            },
            "resultUrl": {"jsonUrl": "http://x/r.json", "markdownUrl": "http://x/r.md"},
            "errorMsg": None,
        },
    }


def _patched_get(payload: dict[str, Any]) -> Any:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = payload
    return patch.object(ocr_service.requests, "get", return_value=mock_resp)


def test_done_job_is_charged(db: Session) -> None:
    user = _make_user(db)
    _set_balance(db, user.id, 10_000)
    _set_usage(db, user.id, pages_used=50)  # no free pages left
    file, _ = _make_running_job(db, user.id)

    with (
        _patched_get(_ocr_response("done", total_pages=4)),
        patch.object(ocr_service, "upload_ocr_job_result"),
    ):
        state = ocr_service.get_ocr_job_status(file=file, session=db, user=user)

    assert state == OcrJobStatus.DONE
    assert get_or_create_balance(db, user.id).balance == 8_000  # 4 pages * 500
    usage = get_or_create_monthly_usage(
        db, user_id=user.id, year_month=current_year_month()
    )
    assert usage.pages_used == 54
    job = ocr_service.get_file_job_by_file_id(session=db, file_id=file.id)
    assert job is not None and job.billed_at is not None


def test_repoll_done_job_does_not_double_charge(db: Session) -> None:
    user = _make_user(db)
    _set_balance(db, user.id, 10_000)
    _set_usage(db, user.id, pages_used=50)
    file, _ = _make_running_job(db, user.id)

    with (
        _patched_get(_ocr_response("done", total_pages=4)),
        patch.object(ocr_service, "upload_ocr_job_result"),
    ):
        ocr_service.get_ocr_job_status(file=file, session=db, user=user)
    # second poll: job is already DONE + billed; must be a no-op for billing
    ocr_service.get_ocr_job_status(file=file, session=db, user=user)

    assert get_or_create_balance(db, user.id).balance == 8_000
    usage = get_or_create_monthly_usage(
        db, user_id=user.id, year_month=current_year_month()
    )
    assert usage.pages_used == 54


def test_failed_job_is_not_charged(db: Session) -> None:
    user = _make_user(db)
    _set_balance(db, user.id, 10_000)
    _set_usage(db, user.id, pages_used=50)
    file, _ = _make_running_job(db, user.id)

    with _patched_get(_ocr_response("failed")):
        state = ocr_service.get_ocr_job_status(file=file, session=db, user=user)

    assert state == OcrJobStatus.FAILED
    assert get_or_create_balance(db, user.id).balance == 10_000
    usage = get_or_create_monthly_usage(
        db, user_id=user.id, year_month=current_year_month()
    )
    assert usage.pages_used == 50
