from django.conf import settings
from django.utils.translation import get_language

from . import dates


def nepali_today(request):
    today = dates.today_bs()
    nepali = (get_language() or "").startswith("ne")
    return {
        "today_bs": (
            dates.bs_display(today)
            if nepali
            else dates.format_bs(today, "{d} {month_en} {y}")
        ),
        "today_bs_iso": f"{today.year}-{today.month:02d}-{today.day:02d}",
        "current_fy": dates.fiscal_year(today),
        "TAILWIND_CDN": settings.TAILWIND_CDN,
    }
