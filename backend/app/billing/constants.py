"""Billing constants for the monthly free-quota + per-page overage model."""

# Pages each user may process for free per calendar month before overage applies.
FREE_PAGES_PER_MONTH = 50

# Price charged per page beyond the monthly free quota, in VND.
PRICE_PER_PAGE_VND = 500

# Timezone whose calendar month defines the quota window.
VN_TIMEZONE = "Asia/Ho_Chi_Minh"
