"""
Tool: Weather
Fetches current weather using wttr.in (free, no API key needed).
"""

import requests
import logging
from utils.tools import register_tool

logger = logging.getLogger(__name__)

def _get_weather(location: str, units: str = "c") -> str:
    """Get weather for a location via wttr.in."""
    try:
        # Clean location
        location = location.strip().replace(" ", "+")
        format_param = "c" if units.lower().startswith("c") else "f"

        url = f"https://wttr.in/{location}?format=j1"
        response = requests.get(url, timeout=15, headers={"User-Agent": "curl/7.68.0"})
        response.raise_for_status()
        data = response.json()

        current = data.get("current_condition", [{}])[0]
        area = data.get("nearest_area", [{}])[0]

        temp = current.get("temp_C") if format_param == "c" else current.get("temp_F")
        feels = current.get("FeelsLikeC") if format_param == "c" else current.get("FeelsLikeF")
        desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
        humidity = current.get("humidity", "N/A")
        wind = current.get("windspeedKmph", "N/A")
        area_name = area.get("areaName", [{}])[0].get("value", location)
        country = area.get("country", [{}])[0].get("value", "")

        unit = "°C" if format_param == "c" else "°F"

        weather_text = (
            f"🌤️ Weather for {area_name}, {country}:\n"
            f"  • Condition: {desc}\n"
            f"  • Temperature: {temp}{unit} (feels like {feels}{unit})\n"
            f"  • Humidity: {humidity}%\n"
            f"  • Wind: {wind} km/h\n"
        )

        # Add 3-day forecast if available
        forecast = data.get("weather", [])
        if len(forecast) >= 2:
            weather_text += "\n📅 Forecast:\n"
            for day in forecast[:3]:
                date = day.get("date", "")
                max_t = day.get("maxtempC") if format_param == "c" else day.get("maxtempF")
                min_t = day.get("mintempC") if format_param == "c" else day.get("mintempF")
                desc = day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "") if len(day.get("hourly", [])) > 4 else ""
                weather_text += f"  • {date}: {min_t}-{max_t}{unit} {desc}\n"

        return weather_text.strip()

    except requests.exceptions.Timeout:
        return "Weather request timed out. Try a shorter location name."
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return f"Could not get weather: {str(e)}"

register_tool(
    name="weather",
    description="Get current weather and forecast for any location worldwide.",
    args_schema={"location": "string (city or location name)", "units": "string (optional: 'c' for Celsius, 'f' for Fahrenheit, default 'c')"},
    func=_get_weather,
)
