"""Time & Date Skill — timezone-aware time."""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

TIMEZONE_OFFSETS = {
    "UTC": 0, "GMT": 0,
    "LAGOS": 1, "WAT": 1,
    "LONDON": 0,
    "NEW_YORK": -5, "EST": -5, "EASTERN": -5,
    "LOS_ANGELES": -8, "PST": -8, "PACIFIC": -8,
    "CHICAGO": -6, "CST": -6, "CENTRAL": -6,
    "DUBAI": 4, "GST": 4,
    "INDIA": 5.5, "IST": 5.5, "MUMBAI": 5.5,
    "TOKYO": 9, "JST": 9,
    "BEIJING": 8, "SHANGHAI": 8,
    "SYDNEY": 11, "AEST": 10,
    "BERLIN": 1, "CET": 1, "PARIS": 1, "MADRID": 1,
    "MOSCOW": 3, "MSK": 3,
    "SAO_PAULO": -3, "BRT": -3,
}


def run(timezone_name: str = "UTC", format_string: str = "default") -> str:
    """Get current time in a specified timezone."""
    try:
        tz_key = timezone_name.upper().replace(" ", "_")
        offset_hours = TIMEZONE_OFFSETS.get(tz_key, 0)

        now = datetime.now(timezone.utc)
        tz_time = now + timedelta(hours=offset_hours)

        if format_string in ("default", ""):
            formatted = tz_time.strftime("%Y-%m-%d %H:%M:%S")
        elif format_string == "date":
            formatted = tz_time.strftime("%Y-%m-%d")
        elif format_string == "time":
            formatted = tz_time.strftime("%H:%M:%S")
        elif format_string == "full":
            formatted = tz_time.strftime("%A, %B %d, %Y at %I:%M:%S %p")
        else:
            try:
                formatted = tz_time.strftime(format_string)
            except Exception:
                formatted = tz_time.strftime("%Y-%m-%d %H:%M:%S")

        return f"{formatted} (Timezone: {timezone_name or 'UTC'}, UTC{'+' if offset_hours >= 0 else ''}{offset_hours})"

    except Exception as e:
        return f"Error getting time: {str(e)}"
