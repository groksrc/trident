"""
Demo tool that simulates weather data.
In a real workflow, this would call a weather API.
"""

import json
import random
from datetime import datetime


def get_weather(city: str) -> str:
    """
    Get weather data for a city.

    Args:
        city: The city name

    Returns:
        JSON string with weather data
    """
    # Simulated weather data
    conditions = ["sunny", "cloudy", "partly cloudy", "rainy", "stormy"]

    weather = {
        "city": city,
        "temperature_f": random.randint(45, 85),
        "condition": random.choice(conditions),
        "humidity": random.randint(30, 90),
        "wind_mph": random.randint(0, 25),
        "timestamp": datetime.now().isoformat()
    }

    return json.dumps(weather, indent=2)
