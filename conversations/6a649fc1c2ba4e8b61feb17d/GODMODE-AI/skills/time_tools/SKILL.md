---
name: get_time
description: Get current date and time in any timezone. Supports Lagos, London, New York, Tokyo, Dubai, etc.
version: 1.0.0
triggers:
  - what time
  - current time
  - what date
  - what day
  - timezone
  - clock
arguments:
  - name: timezone_name
    type: string
    required: false
    default: "UTC"
    description: Timezone name (LAGOS, LONDON, NEW_YORK, DUBAI, TOKYO, etc.)
  - name: format_string
    type: string
    required: false
    default: "default"
    description: "Format: default, date, time, full, or custom strftime"
---

# Time & Date

Returns the current time in any supported timezone.
Also supports date formatting and countdowns to future dates.
No API key needed — all computed locally.
