from datetime import datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo("Asia/Hong_Kong")


def hkt_date(now: datetime | None = None) -> str:
    return (now or datetime.now(HKT)).astimezone(HKT).date().isoformat()
