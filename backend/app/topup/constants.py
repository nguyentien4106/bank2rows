from typing import TypedDict


class TopupPackageDict(TypedDict):
    id: str
    amount: int
    label: str


TOPUP_PACKAGES: list[TopupPackageDict] = [
    {"id": "20k", "amount": 20_000, "label": "20,000 VND"},
    {"id": "50k", "amount": 50_000, "label": "50,000 VND"},
    {"id": "100k", "amount": 100_000, "label": "100,000 VND"},
    {"id": "200k", "amount": 200_000, "label": "200,000 VND"},
    {"id": "500k", "amount": 500_000, "label": "500,000 VND"},
    {"id": "1000k", "amount": 1_000_000, "label": "1,000,000 VND"},
    {"id": "2000k", "amount": 2_000_000, "label": "2,000,000 VND"},
    {"id": "5000k", "amount": 5_000_000, "label": "5,000,000 VND"},
    {"id": "10000k", "amount": 10_000_000, "label": "10,000,000 VND"},
]

ALLOWED_AMOUNTS: frozenset[int] = frozenset(p["amount"] for p in TOPUP_PACKAGES)

# Loyalty bonus: a percentage of the paid amount is credited *on top* of the
# top-up. Tiers are (minimum amount in VND, bonus percent), highest first.
BONUS_TIERS: list[tuple[int, int]] = [
    (10_000_000, 10),
    (5_000_000, 8),
    (2_000_000, 7),
    (1_000_000, 6),
    (500_000, 5),
]


def bonus_percent_for_amount(amount: int) -> int:
    """Return the bonus percentage applied to a top-up of *amount* VND."""
    for threshold, percent in BONUS_TIERS:
        if amount >= threshold:
            return percent
    return 0


def bonus_for_amount(amount: int) -> int:
    """Return the bonus VND credited on top of a top-up of *amount* VND."""
    return amount * bonus_percent_for_amount(amount) // 100
