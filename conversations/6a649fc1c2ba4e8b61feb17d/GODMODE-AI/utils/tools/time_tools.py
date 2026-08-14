"""
Tool: Time & Date Utilities
Get current time, convert timezones, format dates.
"""

import logging
from datetime import datetime, timezone
from utils.tools import register_tool

logger = logging.getLogger(__name__)

# Common timezone offsets (UTC-based for simplicity)
TIMEZONE_OFFSETS = {
    "UTC": 0, "GMT": 0,
    "LAGOS": 1, "WAT": 1, "LAGOS/NIGERIA": 1,
    "LONDON": 0, "LONDON/UK": 0,
    "NEW_YORK": -5, "EST": -5, "EASTERN": -5,
    "LOS_ANGELES": -8, "PST": -8, "PACIFIC": -8,
    "CHICAGO": -6, "CST": -6, "CENTRAL": -6,
    "DUBAI": 4, "GST": 4,
    "INDIA": 5.5, "IST": 5.5, "MUMBAI": 5.5,
    "TOKYO": 9, "JST": 9,
    "BEIJING": 8, "CST_CHINA": 8, "SHANGHAI": 8,
    "SYDNEY": 11, "AEST": 10,
    "BERLIN": 1, "CET": 1, "PARIS": 1, "MADRID": 1,
    "MOSCOW": 3, "MSK": 3,
    "SAO_PAULO": -3, "BRT": -3,
}

def _get_time(timezone_name: str = "UTC", format_string: str = "default") -> str:
    """Get current time in a specified timezone."""
    try:
        tz_key = timezone_name.upper().replace(" ", "_")
        offset_hours = TIMEZONE_OFFSETS.get(tz_key, 0)

        now = datetime.now(timezone.utc)
        from datetime import timedelta
        tz_time = now + timedelta(hours=offset_hours)

        if format_string == "default" or not format_string:
            formatted = tz_time.strftime("%Y-%m-%d %H:%M:%S")
        elif format_string == "date":
            formatted = tz_time.strftime("%Y-%m-%d")
        elif format_string == "time":
            formatted = tz_time.strftime("%H:%M:%S")
        elif format_string == "full":
            formatted = tz_time.strftime("%A, %B %d, %Y at %I:%M:%S %p")
        else:
            # Try custom format
            try:
                formatted = tz_time.strftime(format_string)
            except Exception:
                formatted = tz_time.strftime("%Y-%m-%d %H:%M:%S")

        tz_display = timezone_name or "UTC"
        return f"🕐 {formatted} (Timezone: {tz_display}, UTC{'+' if offset_hours >= 0 else ''}{offset_hours})"

    except Exception as e:
        return f"Error getting time: {str(e)}"

def _time_until(target_date: str) -> str:
    """Calculate time until a target date (YYYY-MM-DD format)."""
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d")
        now = datetime.now()
        diff = target - now

        if diff.total_seconds() < 0:
            days_ago = abs(diff.days)
            return f"📅 {target_date} was {days_ago} day(s) ago."
        else:
            days = diff.days
            hours = diff.seconds // 3600
            return f"📅 {target_date} is in {days} day(s) and {hours} hour(s)."
    except ValueError:
        return f"Error: Invalid date format. Use YYYY-MM-DD (e.g., 2026-12-31)."
    except Exception as e:
        return f"Error: {str(e)}"

register_tool(
    name="get_time",
    description="Get current date and time in any timezone. Supports LAGOS, LONDON, NEW_YORK, DUBAI, TOKYO, etc.",
    args_schema={"timezone_name": "string (timezone name, default 'UTC')", "format_string": "string (optional: 'default', 'date', 'time', 'full', or custom strftime format)"},
    func=_get_time,
)

register_tool(
    name="time_until",
    description="Calculate time until or since a target date.",
    args_schema={"target_date": "string (date in YYYY-MM-DD format, e.g. '2026-12-31')"},
    func=_time_until,
)
