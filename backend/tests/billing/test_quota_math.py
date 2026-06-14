from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.billing.constants import (
    FREE_PAGES_PER_MONTH,
    PRICE_PER_PAGE_VND,
    VN_TIMEZONE,
)
from app.billing.service import (
    chargeable_cost_vnd,
    compute_chargeable_pages,
    current_year_month,
)


def test_constants() -> None:
    assert FREE_PAGES_PER_MONTH == 50
    assert PRICE_PER_PAGE_VND == 500
    assert VN_TIMEZONE == "Asia/Ho_Chi_Minh"


@pytest.mark.parametrize(
    ("used", "job", "expected"),
    [
        (49, 1, 0),  # exactly fills the free quota
        (49, 2, 1),  # one page over
        (50, 3, 3),  # quota already used → all chargeable
        (0, 50, 0),  # full free month in one job
        (0, 51, 1),  # one over in a single job
        (0, 0, 0),  # nothing to charge
        (100, 5, 5),  # well past quota
    ],
)
def test_compute_chargeable_pages(used: int, job: int, expected: int) -> None:
    assert compute_chargeable_pages(used, job) == expected


@pytest.mark.parametrize(
    ("pages", "expected_vnd"),
    [(0, 0), (1, 500), (3, 1500), (10, 5000)],
)
def test_chargeable_cost_vnd(pages: int, expected_vnd: int) -> None:
    assert chargeable_cost_vnd(pages) == expected_vnd


def test_current_year_month_matches_vn_timezone() -> None:
    now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    expected = now_vn.year * 100 + now_vn.month
    assert current_year_month() == expected
