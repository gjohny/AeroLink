
import hashlib
import logging
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html import unescape
from urllib.parse import unquote, urlparse

import requests

from .rec_ranker import rank_recommendations


GEOCODING_URL = "https://api.geoapify.com/v1/geocode/search"
PLACES_URL = "https://api.geoapify.com/v2/places"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
MAPILLARY_IMAGES_URL = "https://graph.mapillary.com/images"

logger = logging.getLogger(__name__)


# Default categories for each recommendation tab.
PLACE_CATEGORIES = {
    "activities": (
        "tourism.attraction,"
        "tourism.sights,"
        "entertainment.museum"
    ),
    "restaurants": "catering.restaurant",
    "accommodation": "accommodation.hotel",
}


# Additional categories based on trip interests.
# Unsupported Geoapify categories are automatically
# removed if the API explicitly rejects them.
INTEREST_SEARCH_CATEGORIES = {
    "Museums": [
        "entertainment.museum",
    ],
    "History": [
        "tourism.sights",
    ],
    "Art": [
        "entertainment.museum",
        "tourism.attraction",
    ],
    "Architecture": [
        "tourism.sights",
    ],
    "Nature": [
        "leisure.park",
    ],
    "Beaches": [
        "beach",
    ],
    "Hiking": [
        "sport.hiking",
        "natural",
    ],
    "Shopping": [
        "commercial.shopping_mall",
    ],
    "Nightlife": [
        "catering.bar",
    ],
    "Family Activities": [
        "entertainment.zoo",
        "entertainment.theme_park",
    ],
    "Wildlife": [
        "entertainment.zoo",
    ],
    "Theme Parks": [
        "entertainment.theme_park",
    ],
    "Relaxation": [
        "leisure.park",
    ],
    "Local Culture": [
        "tourism.sights",
        "entertainment.museum",
    ],
}


# Additional accommodation categories based on
# the user's trip-specific lodging preferences.
ACCOMMODATION_SEARCH_CATEGORIES = {
    "Hotel": [
        "accommodation.hotel",
    ],
    "Resort": [
        "accommodation.hotel",
    ],
    "Apartment": [
        "accommodation.apartment",
    ],
    "Hostel": [
        "accommodation.hostel",
    ],
    "Vacation Rental": [
        "accommodation.apartment",
    ],
    "Bed & Breakfast": [
        "accommodation.bed_and_breakfast",
    ],
    "Guesthouse": [
        "accommodation.guest_house",
    ],
    "Cabin": [
        "accommodation.chalet",
    ],
    "Cottage": [
        "accommodation.chalet",
    ],
}


# Small objects that can overwhelm sightseeing results.
MINOR_ACTIVITY_CATEGORIES = (
    "tourism.attraction.artwork",
    "tourism.attraction.fountain",
)


def get_api_key():
    key = os.getenv("GEOAPIFY_API_KEY")

    if not key:
        raise RuntimeError(
            "GEOAPIFY_API_KEY is missing"
        )

    return key


def geocode_destination(destination):
    """Convert a destination into coordinates."""
    response = requests.get(
        GEOCODING_URL,
        params={
            "text": destination,
            "limit": 1,
            "apiKey": get_api_key(),
        },
        timeout=15,
    )

    response.raise_for_status()

    features = response.json().get("features", [])

    if not features:
        return None

    lon, lat = features[0]["geometry"]["coordinates"]

    return {
        "latitude": lat,
        "longitude": lon,
    }


def distance_km(lat1, lon1, lat2, lon2):
    """Calculate approximate distance between coordinates."""
    radius = 6371

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return 2 * radius * math.asin(
        min(1, math.sqrt(a))
    )


def activity_score(categories):
    """
    Assign a general sightseeing quality score.

    This is used as a tiebreaker after preference
    matching, not as the primary ranking factor.
    """
    categories = set(categories)

    score = 0

    if "entertainment.museum" in categories:
        score += 5

    if "tourism.sights" in categories:
        score += 3

    if "tourism.attraction" in categories:
        score += 2

    if any(
        category.startswith(prefix)
        for category in categories
        for prefix in MINOR_ACTIVITY_CATEGORIES
    ):
        score -= 5

    return score


def get_search_categories(category, preferences=None):
    """
    Build a category query using the trip preferences.
    """
    preferences = (
        preferences
        if isinstance(preferences, dict)
        else {}
    )

    categories = set(
        PLACE_CATEGORIES[category].split(",")
    )

    if category == "activities":
        interests = preferences.get("interests", [])

        if isinstance(interests, list):
            for interest in interests:
                categories.update(
                    INTEREST_SEARCH_CATEGORIES.get(
                        interest, []
                    )
                )

    elif category == "accommodation":
        types = preferences.get(
            "accommodation_types", []
        )

        if isinstance(types, list):
            for accommodation_type in types:
                categories.update(
                    ACCOMMODATION_SEARCH_CATEGORIES.get(
                        accommodation_type, []
                    )
                )

    return ",".join(sorted(categories))


def request_places(
    lon,
    lat,
    categories,
    candidate_limit,
):
    """
    Request Geoapify places.

    If Geoapify identifies an unsupported category,
    remove that category and retry.

    Other errors are raised normally.
    """
    active_categories = list(dict.fromkeys(
        value.strip()
        for value in categories.split(",")
        if value.strip()
    ))

    while active_categories:
        response = requests.get(
            PLACES_URL,
            params={
                "categories": ",".join(active_categories),
                "filter": (
                    f"circle:{lon},{lat},10000"
                ),
                "bias": (
                    f"proximity:{lon},{lat}"
                ),
                "limit": candidate_limit,
                "apiKey": get_api_key(),
            },
            timeout=15,
        )

        if response.ok:
            return response.json()

        error_message = ""

        try:
            error_data = response.json()

            if isinstance(error_data, dict):
                error_message = str(
                    error_data.get("message", "")
                )

        except ValueError:
            pass

        # Example:
        # Category "entertainment.nightclub"
        # is not supported.
        match = re.search(
            r'Category ["\']([^"\']+)["\'] is not supported',
            error_message,
            flags=re.IGNORECASE,
        )

        if response.status_code == 400 and match:
            invalid_category = match.group(1)

            if invalid_category in active_categories:
                logger.warning(
                    "Geoapify rejected unsupported "
                    "category '%s'. Retrying without it.",
                    invalid_category,
                )

                active_categories.remove(
                    invalid_category
                )

                continue

        # Authentication errors, rate limits, network
        # problems, and other invalid parameters should
        # not be silently ignored.
        response.raise_for_status()

    raise RuntimeError(
        "No supported Geoapify categories remain."
    )



def commons_file_title(tags):
    """Only use an explicitly linked Commons file, not a name-based guess."""
    value = tags.get("wikimedia_commons") or tags.get("image")
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.hostname not in ("commons.wikimedia.org", "upload.wikimedia.org"):
            return None
        if "/wiki/File:" in parsed.path:
            value = unquote(parsed.path.split("/wiki/", 1)[1])
        elif "/wiki/Special:FilePath/" in parsed.path:
            value = "File:" + unquote(parsed.path.split("/wiki/Special:FilePath/", 1)[1])
        else:
            return None
    if value.startswith("Category:"):
        return None
    if not value.startswith("File:"):
        value = "File:" + value
    return value if len(value) <= 250 else None


def _photo_from_info(info):
    url = info.get("thumburl") or info.get("url") or ""
    if not url.startswith("https://"):
        return None
    metadata = info.get("extmetadata") or {}
    license_name = metadata.get("LicenseShortName", {}).get("value", "")
    artist = metadata.get("Artist", {}).get("value", "")
    artist = unescape(re.sub(r"<[^>]*>", "", artist)).strip()[:150]
    credit = " · ".join(part for part in (artist, license_name) if part)
    return {
        "photo_url": url,
        "photo_credit": credit or "Wikimedia Commons",
        "photo_source_url": info.get("descriptionurl", ""),
    }


COMMONS_HEADERS = {
    # Replace with a real contact email before deploying publicly.
    "User-Agent": "AeroLinkTravelApp/1.0 (student travel recommendations; contact: example@example.com)"
}


def _searchable_words(text):
    return set(re.findall(r"[a-z0-9]{3,}", unescape(str(text)).casefold())) - {
        "the", "and", "rome", "italy", "roma", "photo", "image", "file", "jpg", "jpeg", "png", "webp"
    }


@lru_cache(maxsize=512)
def search_commons_photo(name):
    """Conservative filename match for a named attraction; never guess a business photo."""
    words = _searchable_words(name)
    if not words:
        return None
    try:
        response = requests.get(
            COMMONS_API_URL,
            params={
                "action": "query", "format": "json", "generator": "search",
                "gsrsearch": f'intitle:"{name}" filetype:bitmap',
                "gsrnamespace": 6, "gsrlimit": 8,
                "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 900,
            },
            headers=COMMONS_HEADERS,
            timeout=6,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        matches = []
        for page in pages.values():
            title = page.get("title", "")
            # Require every meaningful name token in the file title.
            # This is a cautious heuristic, not verification of the image content.
            if not words.issubset(_searchable_words(title)):
                continue
            info = (page.get("imageinfo") or [{}])[0]
            photo = _photo_from_info(info)
            if photo:
                matches.append((len(_searchable_words(title) - words), photo))
        return min(matches, key=lambda item: item[0])[1] if matches else None
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        logger.warning("Commons name search failed for %s: %s", name, exc)
        return None


def attach_commons_photos(places):
    """Try OSM-linked files, then cautious name searches for attractions."""
    titles = {}
    for place in places:
        title = commons_file_title(place.get("_photo_tags", {}))
        if title:
            titles.setdefault(title, []).append(place)
    for place in places:
        place.pop("_photo_tags", None)
        place.update(photo_url="", photo_credit="", photo_source_url="")

    if titles:
        try:
            response = requests.get(
                COMMONS_API_URL,
                params={
                    "action": "query", "format": "json", "prop": "imageinfo",
                    "iiprop": "url|extmetadata", "iiurlwidth": 900,
                    "titles": "|".join(titles),
                },
                headers=COMMONS_HEADERS,
                timeout=8,
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            for page in pages.values():
                info = (page.get("imageinfo") or [{}])[0]
                photo = _photo_from_info(info)
                if photo:
                    for place in titles.get(page.get("title"), []):
                        place.update(photo)
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            logger.warning("Wikimedia linked-photo lookup failed: %s", exc)

    # Do not infer photos for restaurants or hotels from name search.
    missing = [p for p in places if not p["photo_url"] and p.get("category") == "activities"][:10]
    if missing:
        with ThreadPoolExecutor(max_workers=4) as executor:
            photos = list(executor.map(lambda p: search_commons_photo(p["name"]), missing))
        for place, photo in zip(missing, photos):
            if photo:
                place.update(photo)
    logger.info("Wikimedia photos matched: %d of %d", sum(bool(p["photo_url"]) for p in places), len(places))



# Mapillary provides street-level imagery near a location, not verified
# photographs of a particular business. Never describe these as place photos.
MAPILLARY_MAX_DISTANCE_METERS = 65


@lru_cache(maxsize=512)
def _mapillary_images_near(cell_lat, cell_lon):
    """Retrieve a small image sample for a roughly 100m location cell."""
    token = os.getenv("MAPILLARY_ACCESS_TOKEN", "").strip()
    if not token:
        return ()

    # The small search box keeps images local and avoids a city-wide query.
    # Bounding boxes are longitude,latitude,longitude,latitude.
    delta = 0.0011
    bbox = (
        f"{cell_lon - delta:.6f},{cell_lat - delta:.6f},"
        f"{cell_lon + delta:.6f},{cell_lat + delta:.6f}"
    )
    try:
        response = requests.get(
            MAPILLARY_IMAGES_URL,
            params={
                "access_token": token,
                "fields": "id,geometry,thumb_1024_url,creator",
                "bbox": bbox,
                "limit": 100,
            },
            timeout=8,
        )
        response.raise_for_status()
        return tuple(response.json().get("data", []))
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("Mapillary image search failed: %s", exc)
        return ()


def _mapillary_photo_for_place(place):
    """Choose the closest usable street-level image within 65 meters."""
    try:
        lat = float(place["latitude"])
        lon = float(place["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    # Round for reuse across places in the same small area.
    images = _mapillary_images_near(round(lat, 3), round(lon, 3))
    nearest = None
    for entry in images:
        url = entry.get("thumb_1024_url") or ""
        coordinates = (entry.get("geometry") or {}).get("coordinates")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
            continue
        try:
            distance = distance_km(lat, lon, float(coordinates[1]), float(coordinates[0])) * 1000
        except (TypeError, ValueError):
            continue
        if distance > MAPILLARY_MAX_DISTANCE_METERS:
            continue
        if nearest is None or distance < nearest[0]:
            nearest = (distance, entry, url)

    if nearest is None:
        return None
    _, entry, url = nearest
    creator = entry.get("creator") or {}
    creator_name = creator.get("username") or creator.get("name") if isinstance(creator, dict) else ""
    credit = "Nearby street view · Mapillary"
    if creator_name:
        credit += f" · {str(creator_name)[:80]}"
    image_id = str(entry.get("id", ""))
    return {
        "photo_url": url,
        "photo_credit": credit,
        "photo_source_url": f"https://www.mapillary.com/app/?pKey={image_id}" if image_id.isdigit() else "https://www.mapillary.com/",
    }


def attach_mapillary_photos(places):
    """Fill only places still missing a Wikimedia photograph."""
    missing = [place for place in places if not place.get("photo_url")]
    if not missing:
        return
    if not os.getenv("MAPILLARY_ACCESS_TOKEN", "").strip():
        logger.info("Mapillary skipped: MAPILLARY_ACCESS_TOKEN not set")
        return
    with ThreadPoolExecutor(max_workers=5) as executor:
        photos = list(executor.map(_mapillary_photo_for_place, missing))
    for place, photo in zip(missing, photos):
        if photo:
            place.update(photo)
    logger.info("Mapillary nearby images matched: %d of %d", sum(bool(p) for p in photos), len(missing))


# OSM prices are community-maintained, not live vendor quotes.
# Only use unambiguous admission charges for activities. Hotel and
# restaurant charges are too context-dependent to infer from these tags.
_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}
_CURRENCY_CODES = {"EUR", "USD", "GBP", "CAD", "AUD", "JPY", "CHF", "INR"}


def extract_osm_price(raw_tags, category):
    """Return safe, structured price metadata for a recommendation."""
    unavailable = {
        "price_amount": None,
        "price_currency": None,
        "price_unit": None,
        "price_type": "unavailable",
        "price_display": "Price unavailable",
        "price_source": None,
    }
    if category != "activities" or not isinstance(raw_tags, dict):
        return unavailable

    fee = str(raw_tags.get("fee") or "").strip().lower()
    if fee in ("no", "false", "0"):
        return {
            **unavailable,
            "price_amount": 0,
            "price_type": "osm_reported",
            "price_unit": "admission",
            "price_display": "Free admission (OSM)",
            "price_source": "OpenStreetMap",
        }

    # 'charge' can describe parking or other services, so accept only
    # charge:admission, or a general charge with fee=yes.
    charge = raw_tags.get("charge:admission")
    if charge is None and fee in ("yes", "true", "1"):
        charge = raw_tags.get("charge")

    if isinstance(charge, str):
        value = charge.strip()
        # Accept only simple, explicit currency amounts, optionally
        # followed by /person or /adult. Do not parse ranges or discounts.
        pattern = r"(?:(EUR|USD|GBP|CAD|AUD|JPY|CHF|INR)\s*(\d+(?:[.,]\d{1,2})?)|([€$£])\s*(\d+(?:[.,]\d{1,2})?))(?:\s*/\s*(?:person|adult))?"
        match = re.fullmatch(pattern, value, flags=re.IGNORECASE)
        if match:
            if match.group(1):
                currency = match.group(1).upper()
                amount_text = match.group(2)
            else:
                currency = {"€": "EUR", "$": "USD", "£": "GBP"}[match.group(3)]
                amount_text = match.group(4)
            amount = float(amount_text.replace(",", "."))
            if amount >= 0:
                amount_label = f"{amount:g}"
                prefix = _CURRENCY_SYMBOLS.get(currency)
                display_amount = f"{prefix}{amount_label}" if prefix else f"{amount_label} {currency}"
                return {
                    **unavailable,
                    "price_amount": amount,
                    "price_currency": currency,
                    "price_unit": "admission",
                    "price_type": "osm_reported",
                    "price_display": f"{display_amount} admission (OSM)",
                    "price_source": "OpenStreetMap",
                }

    if fee in ("yes", "true", "1"):
        return {
            **unavailable,
            "price_type": "fee_applies",
            "price_display": "Admission fee applies · amount unavailable",
            "price_source": "OpenStreetMap",
        }
    return unavailable



# Illustrative budgeting assumptions, NOT observed prices for any venue.
# USD ranges are intentionally broad and are not destination-adjusted.
# Replace with destination-specific sourced estimates when available.
PLANNING_RANGES_USD = {
    "activities": (10, 40, "per person (admission)"),
    "restaurants": (15, 45, "per person (meal)"),
    "accommodation": (80, 220, "per room/night"),
}


def with_planning_estimate(price, category):
    """Add a clearly labelled illustrative range when no amount is known."""
    if price.get("price_amount") is not None:
        return price
    if category not in PLANNING_RANGES_USD:
        return price
    low, high, unit = PLANNING_RANGES_USD[category]
    return {
        **price,
        # No exact numeric price: don't let future budget logic mistake
        # the midpoint of an assumption for a real venue quote.
        "price_amount": None,
        "price_currency": "USD",
        "price_unit": unit,
        "price_type": "planning_estimate",
        "price_display": f"Planning estimate: ${low}–${high} USD {unit}",
        "price_source": "AeroLink illustrative budget assumption (not venue pricing)",
        "price_estimate_min": low,
        "price_estimate_max": high,
        "price_estimate_currency": "USD",
    }


def get_places(
    destination,
    category,
    limit=20,
    preferences=None,
    feedback_records=None,
    excluded_ids=None,
):
    """
    Retrieve and rank destination recommendations.

    Steps:
    1. Geocode the destination.
    2. Choose categories using trip preferences.
    3. Retrieve a larger candidate pool.
    4. Remove duplicates.
    5. Rank candidates by preference relevance.
    6. Select geographically diverse results.
    """
    if category not in PLACE_CATEGORIES:
        raise ValueError(
            "Invalid recommendation category"
        )

    preferences = (
        preferences
        if isinstance(preferences, dict)
        else {}
    )

    location = geocode_destination(destination)

    if not location:
        return []

    lon = location["longitude"]
    lat = location["latitude"]

    # Fetch more candidates than we intend to display.
    candidate_limit = min(
        max(limit * 10, 100),
        500,
    )

    search_categories = get_search_categories(
        category,
        preferences,
    )

    data = request_places(
        lon=lon,
        lat=lat,
        categories=search_categories,
        candidate_limit=candidate_limit,
    )

    excluded_ids = set(excluded_ids or [])
    candidates = []
    seen_names = set()

    for feature in data.get("features", []):
        props = feature.get("properties", {})

        name = props.get("name")
        place_id = props.get("place_id")

        # Geoapify can return numeric names (e.g. a restaurant named 123).
        # Normalize scalar names before deduplication and downstream ranking.
        if isinstance(name, (int, float)) and not isinstance(name, bool):
            name = str(name)
        if not isinstance(name, str) or not name.strip() or not place_id:
            continue
        name = name.strip()

        hashed_id = hashlib.sha256(
            str(place_id).encode("utf-8")
        ).hexdigest()
        if hashed_id in excluded_ids:
            continue

        normalized_name = " ".join(
            name.casefold().split()
        )

        if normalized_name in seen_names:
            continue

        seen_names.add(normalized_name)

        place_lat = props.get("lat")
        place_lon = props.get("lon")

        if place_lat is None or place_lon is None:
            continue

        categories = props.get("categories", [])
        raw_tags = ((props.get("datasource") or {}).get("raw") or {})

        candidates.append({
            "_photo_tags": {
                "wikimedia_commons": raw_tags.get("wikimedia_commons"),
                "image": raw_tags.get("image"),
            },
            "id": hashed_id,
            "name": name,
            "category": category,
            "address": props.get(
                "formatted", ""
            ),
            "latitude": place_lat,
            "longitude": place_lon,
            "categories": categories,
            **with_planning_estimate(extract_osm_price(raw_tags, category), category),
            "website": (
                props.get("website")
                or ((props.get("datasource") or {}).get("raw") or {}).get("website")
                or ""
            ),
            "phone": (
                props.get("contact", {}).get("phone")
                if isinstance(props.get("contact"), dict) else None
            ) or ((props.get("datasource") or {}).get("raw") or {}).get("phone") or "",
            "opening_hours": (
                props.get("opening_hours")
                if isinstance(props.get("opening_hours"), str) else ""
            ) or ((props.get("datasource") or {}).get("raw") or {}).get("opening_hours") or "",
            # Preserve metadata for evidence-based preference matching.
            "catering": props.get("catering") or {},
            "facilities": props.get("facilities") or {},
            "osm_tags": {
                key: value
                for key, value in (
                    (props.get("datasource") or {}).get("raw") or {}
                ).items()
                if key in {
                    "cuisine", "tourism", "historic", "artwork_type",
                    "route", "highway", "sport", "piste:type",
                    "live_music", "music", "event", "leisure",
                    "craft", "hotel", "camp_site", "internet_access",
                    "internet_access:wlan", "wifi", "dogs", "pets_allowed",
                    "wheelchair:rooms",
                }
                or key.startswith("diet:")
                or key in {
                    "parking", "parking:customers", "swimming_pool",
                    "pool", "fitness_centre", "gym", "breakfast:included",
                    "breakfast_included", "kitchen", "self_catering",
                    "air_conditioning", "airport_shuttle", "spa",
                    "sea_view", "ocean_view", "mountain_view",
                    "laundry", "laundry_service", "coworking",
                    "workspace", "desk", "charging_station", "ev_charging",
                    "balcony", "kids_area", "children_welcome",
                    "family_friendly", "wheelchair", "outdoor_seating", "indoor_seating", "pets", "wi_fi", "amenity",
                }
            },
            "_score": (
                activity_score(categories)
                if category == "activities"
                else 0
            ),
        })

    # Rank all retrieved candidates before choosing
    # which 20 places to return.
    candidates = rank_recommendations(
        places=candidates,
        category=category,
        preferences=preferences,
        feedback_records=feedback_records,
    )

    # Preference matches take priority.
    # Sightseeing quality breaks ties.
    candidates.sort(
        key=lambda place: (
            place.get("diet_priority", 0),
            place.get("match_score", 0),
            place.get("_score", 0),
        ),
        reverse=True,
    )

    selected = []
    selected_ids = set()

    # Spread activities around the destination.
    # Use a smaller minimum spacing for hotels
    # and restaurants.
    spacing_levels = (
        (1.0, 0.5, 0.0)
        if category == "activities"
        else (0.2, 0.0)
    )

    from itertools import groupby
    for _, group in groupby(candidates, key=lambda p: (p.get("diet_priority", 0), p.get("match_score", 0))):
        peers = list(group)
        for minimum_spacing in spacing_levels:
            for place in peers:
                if len(selected) >= limit:
                    break
                if place["id"] in selected_ids:
                    continue
                if all(distance_km(place["latitude"], place["longitude"], other["latitude"], other["longitude"]) >= minimum_spacing for other in selected):
                    selected.append(place)
                    selected_ids.add(place["id"])
            if len(selected) >= limit:
                break
        if len(selected) >= limit:
            break

    # Remove internal-only scoring data.
    # Keep match_score, matched_preferences, and why
    # for the frontend.
    for place in selected:
        place.pop("_score", None)

    attach_commons_photos(selected)
    attach_mapillary_photos(selected)
    return selected
