from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser, SessionDep
from app.topup.constants import (
    TOPUP_PACKAGES,
    bonus_for_amount,
    bonus_percent_for_amount,
)
from app.topup.schemas import (
    TopupPackage,
    TopupPackagesResponse,
    TopupTransactionPublic,
    UserBalancePublic,
)
from app.topup.service import get_balance, get_transaction_history

router = APIRouter(prefix="/topup", tags=["topup"])


@router.get("/packages", response_model=TopupPackagesResponse)
def get_topup_packages(_current_user: CurrentUser) -> Any:
    """Return the list of available top-up packages with their loyalty bonus."""
    return TopupPackagesResponse(
        packages=[
            TopupPackage(
                **p,
                bonus_percent=bonus_percent_for_amount(p["amount"]),
                bonus_amount=bonus_for_amount(p["amount"]),
            )
            for p in TOPUP_PACKAGES
        ]
    )


@router.get("/balance", response_model=UserBalancePublic)
def get_my_balance(session: SessionDep, current_user: CurrentUser) -> Any:
    """Return the current balance for the authenticated user."""
    balance = get_balance(session, user_id=current_user.id)
    return UserBalancePublic(
        user_id=balance.user_id,
        balance=balance.balance,
        updated_at=balance.updated_at,
    )


@router.get("/transactions", response_model=list[TopupTransactionPublic])
def get_my_transactions(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 50,
) -> Any:
    """Return paginated transaction history for the authenticated user."""
    return get_transaction_history(
        session, user_id=current_user.id, skip=skip, limit=limit
    )
