---
name: weather
description: Get current weather and 3-day forecast for any location worldwide
version: 1.0.0
triggers:
  - weather
  - temperature
  - forecast
  - how hot
  - how cold
  - is it raining
arguments:
  - name: location
    type: string
    required: true
    description: City or location name
  - name: units
    type: string
    required: false
    default: "c"
    description: "c for Celsius, f for Fahrenheit"
---

# Weather

Fetches current weather conditions and a 3-day forecast using the free wttr.in API.
No API key required. Works for any city worldwide.
