"""Weather from `Open-Meteo <https://open-meteo.com>`_ — free, no API key."""

from __future__ import annotations

from typing import Any

import httpx

from jarvis_core.domain.errors import JarvisError
from jarvis_core.domain.records import WeatherReport

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: WMO weather interpretation codes → spoken descriptions.
WMO_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "freezing drizzle",
    57: "heavy freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "violent showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "severe thunderstorms with hail",
}


class OpenMeteoWeatherProvider:
    """Implements :class:`~jarvis_core.domain.ports.WeatherProvider`.

    Args:
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def current(self, location: str) -> WeatherReport | None:
        """Geocode ``location`` and fetch current conditions."""
        try:
            place = await self._geocode(location)
            if place is None:
                return None
            forecast = await self._client.get(
                FORECAST_URL,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                    "weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "forecast_days": 1,
                    "timezone": "auto",
                },
            )
            forecast.raise_for_status()
            data = forecast.json()
        except httpx.HTTPError as exc:
            raise JarvisError("The weather service is unreachable right now.") from exc

        current = data["current"]
        daily = data.get("daily") or {}
        name = ", ".join(p for p in (place.get("name"), place.get("country")) if p)
        return WeatherReport(
            location=name,
            temperature_c=float(current["temperature_2m"]),
            feels_like_c=float(current["apparent_temperature"]),
            description=WMO_CODES.get(int(current["weather_code"]), "unsettled conditions"),
            wind_kph=float(current["wind_speed_10m"]),
            humidity_pct=float(current["relative_humidity_2m"]),
            high_c=_first(daily.get("temperature_2m_max")),
            low_c=_first(daily.get("temperature_2m_min")),
        )

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()

    async def _geocode(self, location: str) -> dict[str, Any] | None:
        response = await self._client.get(
            GEOCODING_URL, params={"name": location, "count": 1, "language": "en"}
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        return results[0] if results else None


def _first(values: list[float] | None) -> float | None:
    return float(values[0]) if values else None
