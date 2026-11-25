"""Human-friendly dates in Spanish, local time."""

from datetime import UTC, datetime, timedelta

_DAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def clock(when: datetime, now: datetime | None = None) -> str:
    """'13:15' today, '24 nov 13:15' otherwise (local time)."""
    local = when.astimezone()
    local_now = (now or datetime.now(UTC)).astimezone()
    if local.date() == local_now.date():
        return local.strftime("%H:%M")
    year = f" {local.year}" if local.year != local_now.year else ""
    return f"{local.day} {_MONTHS[local.month - 1]}{year} {local:%H:%M}"


def relative(when: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    seconds = (now - when).total_seconds()
    if seconds < 60:
        return "ahora"
    if seconds < 3600:
        return f"hace {int(seconds // 60)} min"
    local, local_now = when.astimezone(), now.astimezone()
    days = (local_now.date() - local.date()).days
    hm = local.strftime("%H:%M")
    if days == 0:
        return f"hoy {hm}"
    if days == 1:
        return f"ayer {hm}"
    if days < 7:
        return f"{_DAYS[local.weekday()]} {hm}"
    month = _MONTHS[local.month - 1]
    if local.year == local_now.year or local_now - local < timedelta(days=180):
        return f"{local.day} {month}"
    return f"{local.day} {month} {local.year}"
