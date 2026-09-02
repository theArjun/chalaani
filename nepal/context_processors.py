from django.conf import settings

from . import dates


def nepali_today(request):
    today = dates.today_bs()
    return {
        "today_bs": dates.bs_display(today),
        "today_bs_iso": f"{today.year}-{today.month:02d}-{today.day:02d}",
        "current_fy": dates.fiscal_year(today),
        "TAILWIND_CDN": settings.TAILWIND_CDN,
    }
