"""Pick the smallest NOAA feed window that covers a requested time span."""
from datetime import datetime, timedelta


def pick_range_file(start: datetime, end: datetime) -> str:
    span = end - start
    if span <= timedelta(hours=6):
        return "6-hour"
    if span <= timedelta(days=1):
        return "1-day"
    if span <= timedelta(days=3):
        return "3-day"
    return "7-day"
