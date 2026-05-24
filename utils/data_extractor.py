import json
import urllib.parse
from typing import Dict, Any, List


def _build_booking_link(base_url: str, booking_token: str) -> str | None:
    """
    Generate direct Google Flights booking/details URL.
    """
    if not base_url or not booking_token:
        return None

    return (
        f"{base_url}&booking_token="
        f"{urllib.parse.quote(booking_token)}"
    )


def _simplify_segment(
    segment: Dict[str, Any],
    flight_meta: Dict[str, Any]
) -> Dict[str, Any]:

    return {
        # Flight-level metadata (flattened into each segment)
        "price": flight_meta["price"],
        "type": flight_meta["type"],
        "total_duration_minutes": flight_meta["total_duration_minutes"],
        "stops": flight_meta["stops"],
        "layovers": flight_meta["layovers"],
        "carbon_emissions_kg": flight_meta["carbon_emissions_kg"],
        "booking_link": flight_meta["booking_link"],

        # Segment-level details
        "from": {
            "airport": segment.get("departure_airport", {}).get("id"),
            "time": segment.get("departure_airport", {}).get("time"),
        },
        "to": {
            "airport": segment.get("arrival_airport", {}).get("id"),
            "time": segment.get("arrival_airport", {}).get("time"),
        },
        "airline": segment.get("airline"),
        "flexibility": segment.get("extensions", []),
        "flight_number": segment.get("flight_number"),
        "duration_minutes": segment.get("duration"),
        "airplane": segment.get("airplane"),
        "travel_class": segment.get("travel_class"),
        "delayed": segment.get("often_delayed_by_over_30_min", False),
    }


def _flatten_itinerary(
    flight_option: Dict[str, Any],
    base_url: str
) -> list[Dict[str, Any]]:

    layovers = flight_option.get("layovers", [])

    flight_meta = {
        "price": f"INR {flight_option.get('price', 0):.2f}",
        "type": flight_option.get("type"),
        "total_duration_minutes": flight_option.get("total_duration"),
        "stops": len(layovers),
        "layovers": [
            {
                "airport": layover.get("id"),
                "duration_minutes": layover.get("duration"),
                "overnight": layover.get("overnight", False),
            }
            for layover in layovers
        ],
        "carbon_emissions_kg": round(
            flight_option.get("carbon_emissions", {})
            .get("this_flight", 0) / 1000
        ),

        "booking_link": _build_booking_link(
            base_url,
            flight_option.get("departure_token") or flight_option.get(
                "booking_token")
        ),
    }

    return [
        _simplify_segment(segment, flight_meta)
        for segment in flight_option.get("flights", [])
    ]


def extract_flights_data(data: Dict[str, Any]) -> list[Dict[str, Any]]:
    """
    Extract and flatten all flight segments from the raw API response.
    Each element in the returned list is a segment enriched with its
    parent itinerary's price, duration, stops, layovers, carbon
    emissions, and booking link.
    """
    base_url = (
        data.get("search_metadata", {})
        .get("google_flights_url")
    )

    all_flights = (
        data.get("best_flights", [])
        + data.get("other_flights", [])
    )

    return [
        segment
        for flight_option in all_flights
        for segment in _flatten_itinerary(flight_option, base_url)
    ]


def _build_google_hotels_link(property_token):
    if not property_token:
        return None

    return f"https://www.google.com/travel/hotels/entity/{property_token}"


def _extract_hotel_details(hotel):

    cleaned = {
        "name": hotel.get("name"),

        "description": hotel.get("description"),

        # Official hotel website
        "official_website": hotel.get("link"),

        # Google Hotels details / booking page
        "google_hotels_link": _build_google_hotels_link(
            hotel.get("property_token")
        ),

        "hotel_class": hotel.get("hotel_class"),

        "rating": {
            "overall_rating": hotel.get("overall_rating"),
            "reviews_count": hotel.get("reviews")
        },

        "price": {
            "per_night": hotel.get("rate_per_night", {}).get("lowest"),
            "before_taxes": hotel.get("rate_per_night", {}).get("before_taxes_fees")
        },

        "deal": hotel.get("deal"),

        "coordinates": hotel.get("gps_coordinates"),

        "check_in": hotel.get("check_in_time"),
        "check_out": hotel.get("check_out_time"),

        "amenities": hotel.get("amenities", [])[:10],

        "nearby_places": hotel.get("nearby_places", [])[:5],

        # Keep only 2 images to save tokens
        "images": [
            img.get("original_image")
            for img in hotel.get("images", [])[:2]
        ]
    }

    return cleaned


def extract_hotels_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    '''
    Extract and simplify hotel data from the raw API response.
    '''

    hotels = data.get("properties", [])
    return [_extract_hotel_details(h) for h in hotels]
