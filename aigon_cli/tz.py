"""Timezone utilities for Aigon CLI.

Uses only standard library. Falls back gracefully if zoneinfo unavailable.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Union

# Try to import zoneinfo (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except ImportError:
    ZoneInfo = None
    ZONEINFO_AVAILABLE = False

# Common timezone abbreviations mapped to IANA names
TZ_ALIASES = {
    'UTC': 'UTC',
    'GMT': 'Etc/GMT',
    'CET': 'Europe/Paris',
    'CEST': 'Europe/Paris',
    'WET': 'Europe/Lisbon',
    'WEST': 'Europe/Lisbon',
    'EET': 'Europe/Helsinki',
    'EEST': 'Europe/Helsinki',
    'EST': 'America/New_York',
    'EDT': 'America/New_York',
    'CST': 'America/Chicago',
    'CDT': 'America/Chicago',
    'MST': 'America/Denver',
    'MDT': 'America/Denver',
    'PST': 'America/Los_Angeles',
    'PDT': 'America/Los_Angeles',
    'JST': 'Asia/Tokyo',
    'IST': 'Asia/Kolkata',
    'SGT': 'Asia/Singapore',
    'HKT': 'Asia/Hong_Kong',
    'AEST': 'Australia/Sydney',
    'AEDT': 'Australia/Sydney',
    'AWST': 'Australia/Perth',
    'NZST': 'Pacific/Auckland',
    'NZDT': 'Pacific/Auckland',
}

# Fixed UTC offsets for common abbreviations (fallback if zoneinfo unavailable)
TZ_OFFSETS = {
    'UTC': 0,
    'GMT': 0,
    'CET': 1,
    'CEST': 2,
    'WET': 0,
    'WEST': 1,
    'EET': 2,
    'EEST': 3,
    'EST': -5,
    'EDT': -4,
    'CST': -6,
    'CDT': -5,
    'MST': -7,
    'MDT': -6,
    'PST': -8,
    'PDT': -7,
    'JST': 9,
    'IST': 5.5,
    'SGT': 8,
    'HKT': 8,
    'AEST': 10,
    'AEDT': 11,
    'AWST': 8,
    'NZST': 12,
    'NZDT': 13,
}


def get_timezone(tz_str: str) -> Optional[Union['ZoneInfo', timezone]]:
    """Get timezone from string.

    Supports:
    - IANA names: Europe/London, America/New_York
    - Abbreviations: UTC, CET, EST, PST, etc.

    Args:
        tz_str: Timezone string

    Returns:
        timezone object or None if not recognized
    """
    if not tz_str:
        return None

    tz_str = tz_str.strip()
    tz_upper = tz_str.upper()

    # Try zoneinfo first (more accurate for DST)
    if ZONEINFO_AVAILABLE:
        # Check aliases
        if tz_upper in TZ_ALIASES:
            try:
                return ZoneInfo(TZ_ALIASES[tz_upper])
            except Exception:
                pass

        # Try as IANA name directly
        try:
            return ZoneInfo(tz_str)
        except Exception:
            pass

    # Fallback to fixed offsets
    if tz_upper in TZ_OFFSETS:
        offset_hours = TZ_OFFSETS[tz_upper]
        if isinstance(offset_hours, float):
            # Handle fractional hours (e.g., IST +5:30)
            hours = int(offset_hours)
            minutes = int((offset_hours - hours) * 60)
            return timezone(timedelta(hours=hours, minutes=minutes))
        else:
            return timezone(timedelta(hours=offset_hours))

    return None


def parse_time(time_str: str, base_date: datetime = None) -> datetime:
    """Parse time string to datetime.

    Supports formats:
    - HH:MM (e.g., 10:35)
    - HH:MM:SS (e.g., 10:35:00)
    - HH:MM TZ (e.g., 10:35 CET, 10:35 Europe/London)

    Args:
        time_str: Time string with optional timezone
        base_date: Date to use (default: today UTC)

    Returns:
        datetime object in UTC

    Raises:
        ValueError: If time format is invalid or timezone not recognized
    """
    if base_date is None:
        base_date = datetime.now(timezone.utc)

    time_str = time_str.strip()
    tz = timezone.utc

    # Check for timezone suffix (space-separated)
    parts = time_str.split()
    if len(parts) >= 2:
        time_part = parts[0]
        tz_part = ' '.join(parts[1:])
        parsed_tz = get_timezone(tz_part)
        if parsed_tz is None:
            raise ValueError(f"Unknown timezone: {tz_part}")
        tz = parsed_tz
    else:
        time_part = time_str

    # Parse time component
    time_parts = time_part.split(':')
    if not time_parts:
        raise ValueError(f"Invalid time format: {time_str}")

    try:
        hour = int(time_parts[0])
        minute = int(time_parts[1]) if len(time_parts) > 1 else 0
        second = int(time_parts[2]) if len(time_parts) > 2 else 0
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}")

    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError(f"Invalid time values: {time_str}")

    # Create datetime in the specified timezone
    # Use base_date for year/month/day, but specified timezone
    local_dt = datetime(
        base_date.year, base_date.month, base_date.day,
        hour, minute, second,
        tzinfo=tz
    )

    # Convert to UTC
    return local_dt.astimezone(timezone.utc)


def parse_time_range(time_range: str, base_date: datetime = None) -> tuple:
    """Parse time range string to (start_ts, end_ts) timestamps.

    Supports formats:
    - HH:MM-HH:MM (e.g., 10:35-10:50)
    - HH:MM-HH:MM TZ (e.g., 10:35-10:50 CET)

    Args:
        time_range: Time range string
        base_date: Date to use (default: today UTC)

    Returns:
        (start_ts, end_ts) tuple of Unix timestamps
    """
    if '-' not in time_range:
        raise ValueError(f"Invalid time range format: {time_range}. Expected HH:MM-HH:MM")

    # Handle timezone at the end
    parts = time_range.strip().split()
    tz_suffix = ''
    if len(parts) >= 2:
        # Last part might be timezone
        range_part = parts[0]
        tz_suffix = ' ' + ' '.join(parts[1:])
    else:
        range_part = time_range.strip()

    # Split the range
    if '-' not in range_part:
        raise ValueError(f"Invalid time range format: {time_range}")

    start_str, end_str = range_part.split('-', 1)

    # Add timezone suffix to both times
    start_dt = parse_time(start_str + tz_suffix, base_date)
    end_dt = parse_time(end_str + tz_suffix, base_date)

    return int(start_dt.timestamp()), int(end_dt.timestamp())
