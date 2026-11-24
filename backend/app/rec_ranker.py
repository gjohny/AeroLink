"""Evidence-based ranking of Geoapify places, with persistent trip feedback."""
import re

INTEREST_CATEGORIES = {
    "Museums": ["entertainment.museum"],
    "History": ["tourism.sights.memorial", "tourism.sights.archaeological_site", "building.historic"],
    "Art": ["tourism.attraction.artwork"],
    "Architecture": ["building.historic"],
    "Nature": ["natural", "leisure.park"],
    "Beaches": ["beach", "natural.beach"],
    "Shopping": ["commercial.shopping_mall"],
    "Nightlife": ["catering.bar"],
    "Family Activities": ["entertainment.zoo", "entertainment.theme_park"],
    "Wildlife": ["entertainment.zoo"],
    "Theme Parks": ["entertainment.theme_park"],
    "Relaxation": ["leisure.park"],
    "Local Culture": [],
}

# Extra evidence from OSM tags. These are deliberately conservative: we do
# not infer an interest from a place name or an unrelated generic category.
INTEREST_TAGS = {
    "History": {"historic": {"yes", "monument", "memorial", "castle", "ruins", "archaeological_site", "fort", "city_gate"}},
    "Art": {"tourism": {"artwork", "gallery"}, "artwork_type": None},
    "Architecture": {"historic": {"castle", "fort", "city_gate", "manor", "palace"}},
    "Hiking": {"route": {"hiking"}, "sport": {"hiking"}},
    "Camping": {"tourism": {"camp_site", "caravan_site"}},
    "Cycling": {"route": {"bicycle"}},
    "Water Sports": {"sport": {"surfing", "sailing", "canoe", "kayaking", "windsurfing"}},
    "Skiing": {"sport": {"skiing"}, "piste:type": None},
    "Live Music": {"live_music": {"yes"}, "music": {"live"}},
    "Festivals": {"event": {"festival"}},
    "Sports": {"leisure": {"sports_centre", "stadium", "pitch"}},
    "Wellness": {"leisure": {"spa", "sauna"}},
    "Food Tours": {"tourism": {"food_tour"}},
    "Boat Tours": {"tourism": {"boat_tour"}},
    "Cooking Classes": {"craft": {"cooking"}},
    "Stargazing": {"tourism": {"observatory"}},
}

ACCOMMODATION_CATEGORIES = {
    "Hotel": ["accommodation.hotel"],
    "Resort": ["accommodation.hotel.resort"],
    "Apartment": ["accommodation.apartment"],
    "Hostel": ["accommodation.hostel"],
    "Vacation Rental": ["accommodation.apartment", "accommodation.chalet"],
    "Bed & Breakfast": ["accommodation.bed_and_breakfast"],
    "Guesthouse": ["accommodation.guest_house"],
    "Cabin": ["accommodation.chalet"],
    "Cottage": ["accommodation.chalet"],
}

# Direct OSM evidence for accommodation subtypes; never assume all hotels
# are boutique/luxury or all guesthouses are homestays.
ACCOMMODATION_TAGS = {
    "Resort": {"tourism": {"resort"}},
    "Boutique Hotel": {"hotel": {"boutique"}},
    "Luxury Hotel": {"hotel": {"luxury"}},
    "Glamping": {"camp_site": {"glamping"}},
    "Homestay": {"tourism": {"homestay"}},
    "Eco-Lodge": {"tourism": {"eco_lodge", "ecolodge"}},
    "Farm Stay": {"tourism": {"farmstay", "farm_stay"}},
}

# Geoapify and OSM diet tags: positive values indicate that the venue
# advertises the option, not that it is allergen-safe or certified.
DIET_TAGS = {
    "Vegetarian": ["vegetarian"], "Vegan": ["vegan"],
    "Halal": ["halal"], "Kosher": ["kosher"],
    "Gluten-Free": ["gluten_free", "gluten-free"],
    "Dairy-Free": ["lactose_free", "dairy_free"],
    "Nut-Free": ["nut_free"], "Pescatarian": ["pescetarian", "pescatarian"],
    "Egg-Free": ["egg_free"], "Soy-Free": ["soy_free"],
    "Shellfish-Free": ["shellfish_free"], "Low-Sodium": ["low_sodium"],
    "Jain": ["jain"], "No Pork": ["no_pork", "pork_free"],
}

# Each amenity needs an explicit positive value. 'internet_access=yes' does
# not imply free Wi-Fi; it supports Wi-Fi only when wireless is specified.
AMENITY_TAGS = {
    "Wi-Fi": ["internet_access:wlan", "wifi", "wi_fi"],
    "Parking": ["parking", "parking:customers"],
    "Pool": ["swimming_pool", "pool"],
    "Gym": ["fitness_centre", "gym"],
    "Breakfast Included": ["breakfast:included", "breakfast_included"],
    "Pet-Friendly": ["dogs", "pets_allowed", "pets"],
    "Kitchen": ["kitchen", "self_catering"],
    "Air Conditioning": ["air_conditioning"],
    "Airport Shuttle": ["airport_shuttle"],
    "Spa": ["spa"],
    "Ocean View": ["sea_view", "ocean_view"],
    "Mountain View": ["mountain_view"],
    "Laundry": ["laundry", "laundry_service"],
    "Workspace": ["coworking", "workspace", "desk"],
    "EV Charging": ["charging_station", "ev_charging"],
    "Accessible Rooms": ["wheelchair", "wheelchair:rooms"],
    "Balcony": ["balcony"],
    "Child-Friendly": ["kids_area", "children_welcome", "family_friendly"],
}

GENERIC_FEEDBACK_CATEGORIES = {
    "tourism", "tourism.attraction", "tourism.sights", "catering",
    "catering.restaurant", "accommodation", "accommodation.hotel",
    "entertainment",
}


def normalize(value):
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def category_matches(categories, prefix):
    return any(c == prefix or c.startswith(prefix + ".") for c in categories)


def get_selections(preferences, key):
    values = preferences.get(key, [])
    return list({normalize(v): v.strip() for v in values if isinstance(v, str) and v.strip()}.values()) if isinstance(values, list) else []


def positive(value):
    return value is True or (isinstance(value, str) and normalize(value) in {"yes", "true", "1", "designated", "only", "free"})


def tag_matches(tags, rules):
    for key, accepted in rules.items():
        value = tags.get(key)
        if value is None:
            continue
        if accepted is None and normalize(value) not in {"", "no", "false", "0"}:
            return True
        if accepted is not None and normalize(value) in accepted:
            return True
    return False


def cuisine_matches(place, cuisine):
    wanted = normalize(cuisine).replace(" ", "_")
    aliases = {
        "bbq": {"bbq", "barbecue"},
        "seafood": {"seafood", "fish"},
        "middle_eastern": {"middle_eastern", "arab", "levantine"},
    }
    tokens = aliases.get(wanted, {wanted})
    categories = [normalize(c) for c in place.get("categories", []) if isinstance(c, str)]
    if any(c.startswith("catering.restaurant.") and c.split(".")[-1] in tokens for c in categories):
        return True
    tags = place.get("osm_tags") or {}
    raw = tags.get("cuisine", "")
    raw_tokens = {normalize(x).replace(" ", "_") for x in re.split(r"[;,]", str(raw))}
    return bool(tokens & raw_tokens)


def diet_matches(place, selection):
    keys = DIET_TAGS.get(selection, [])
    catering = place.get("catering") or {}
    diet = (catering.get("diet") or {}) if isinstance(catering, dict) else {}
    tags = place.get("osm_tags") or {}
    for key in keys:
        if positive(diet.get(key)) or positive(tags.get("diet:" + key)):
            return True
    return False


def amenity_matches(place, selection):
    facilities = place.get("facilities") or {}
    tags = place.get("osm_tags") or {}
    if not isinstance(facilities, dict):
        facilities = {}
    if not isinstance(tags, dict):
        tags = {}
    if selection == "Wi-Fi":
        return (normalize(tags.get("internet_access", "")) == "wlan"
                or positive(tags.get("internet_access:wlan"))
                or positive(tags.get("wifi")) or positive(facilities.get("wifi")))
    if selection == "Pet-Friendly":
        return normalize(tags.get("dogs", "")) in {"yes", "allowed"} or positive(tags.get("pets_allowed"))
    if selection == "Accessible Rooms":
        # General wheelchair accessibility is not proof of accessible rooms.
        return positive(tags.get("wheelchair:rooms"))
    for key in AMENITY_TAGS.get(selection, []):
        if positive(facilities.get(key)) or positive(tags.get(key)):
            return True
    return False


def feedback_similarity(place_categories, liked_categories):
    place_set = {normalize(v) for v in (place_categories or []) if isinstance(v, str)}
    liked_set = {normalize(v) for v in (liked_categories or []) if isinstance(v, str)}
    shared = (place_set & liked_set) - GENERIC_FEEDBACK_CATEGORIES
    return int(any(not any(other.startswith(c + ".") for other in shared) for c in shared))


def feedback_adjustment(place, category, feedback_records):
    score = 0
    for record in feedback_records:
        if not isinstance(record, dict) or record.get("category") != category:
            continue
        direction = {"more": 1, "less": -1}.get(record.get("preference"), 0)
        if not direction:
            continue
        if str(record.get("place_key")) == str(place.get("id")):
            score += direction * 6
        else:
            score += direction * 2 * feedback_similarity(place.get("categories", []), record.get("place_categories", []))
    return max(-12, min(12, score))


def rank_recommendations(places, category, preferences, feedback_records=None):
    if not isinstance(preferences, dict):
        preferences = {}
    if not isinstance(feedback_records, list):
        feedback_records = []
    ranked = []
    for original_place in places:
        place = original_place.copy()
        categories = [normalize(v) for v in place.get("categories", []) if isinstance(v, str)]
        tags = place.get("osm_tags") or {}
        if not isinstance(tags, dict):
            tags = {}
        score = 0
        matches = []
        diet_matches_found = []
        amenities_found = []
        if category == "activities":
            for interest in get_selections(preferences, "interests"):
                prefixes = INTEREST_CATEGORIES.get(interest, [])
                if any(category_matches(categories, p) for p in prefixes) or tag_matches(tags, INTEREST_TAGS.get(interest, {})):
                    score += 3
                    matches.append(interest)
        elif category == "restaurants":
            for cuisine in get_selections(preferences, "cuisines"):
                if cuisine_matches(place, cuisine):
                    score += 3
                    matches.append(cuisine)
            for dietary in get_selections(preferences, "dietary_restrictions"):
                if diet_matches(place, dietary):
                    score += 2
                    diet_matches_found.append(dietary)
        elif category == "accommodation":
            for kind in get_selections(preferences, "accommodation_types"):
                prefixes = ACCOMMODATION_CATEGORIES.get(kind, [])
                # Hotel must not match every specialized hotel subtype.
                category_hit = any(category_matches(categories, p) for p in prefixes)
                if category_hit or tag_matches(tags, ACCOMMODATION_TAGS.get(kind, {})):
                    score += 3
                    matches.append(kind)
            for amenity in get_selections(preferences, "amenities"):
                if amenity_matches(place, amenity):
                    score += 2
                    amenities_found.append(amenity)
        matches = list(dict.fromkeys(matches))
        primary_key = {"activities": "interests", "restaurants": "cuisines", "accommodation": "accommodation_types"}.get(category, "")
        primary = get_selections(preferences, primary_key)
        secondary = get_selections(preferences, "amenities") if category == "accommodation" else []
        groups = [(50, len(matches), len(primary)), (30, len(amenities_found), len(secondary))]
        total = sum(weight for weight, _, count in groups if count)
        preference_score = round(80 * sum(weight * hits / count for weight, hits, count in groups if count) / total, 2) if total else 0
        feedback_score = round(feedback_adjustment(place, category, feedback_records) * 10 / 12, 2)
        requested_diet = get_selections(preferences, "dietary_restrictions") if category == "restaurants" else []
        # Listed dietary options take priority over cuisine and feedback.
        diet_priority = len(diet_matches_found) if requested_diet else 0
        place["diet_priority"] = diet_priority
        if requested_diet:
            diet = (place.get("catering") or {}).get("diet") or {}
            if any(any(normalize(diet.get(k)) in {"no", "false", "0"} or normalize(tags.get("diet:" + k)) in {"no", "false", "0"} for k in DIET_TAGS.get(v, [])) for v in requested_diet):
                continue
        place["match_score"] = preference_score + feedback_score
        place["preference_score"] = preference_score
        place["feedback_score"] = feedback_score
        place["matched_preferences"] = matches
        place["matched_dietary_options"] = diet_matches_found
        place["matched_amenities"] = amenities_found
        # Concise, evidence-based explanations. Only describe explicitly
        # supported matches; unreported metadata is unknown, not negative.
        selected_cuisines = get_selections(preferences, "cuisines")
        selected_interests = get_selections(preferences, "interests")
        selected_lodging = get_selections(preferences, "accommodation_types")
        selected_diet = get_selections(preferences, "dietary_restrictions")
        selected_amenities = get_selections(preferences, "amenities")

        parts = []
        if matches:
            label = {
                "activities": "interests",
                "restaurants": "cuisine preference",
                "accommodation": "accommodation preference",
            }.get(category, "preferences")
            if len(matches) != 1:
                label = {
                    "activities": "interests",
                    "restaurants": "cuisine preferences",
                    "accommodation": "accommodation preferences",
                }.get(category, "preferences")
            parts.append("Matches your " + ", ".join(matches) + " " + label)
        elif category == "restaurants" and selected_cuisines:
            parts.append("No confirmed match for your " + ", ".join(selected_cuisines) + " cuisine preference" + ("s" if len(selected_cuisines) > 1 else ""))
        elif category == "activities" and selected_interests:
            parts.append("No confirmed match for your selected interests")
        elif category == "accommodation" and selected_lodging:
            parts.append("No confirmed match for your selected accommodation types")
        else:
            parts.append("A place in your destination; no specific preference match identified")

        if diet_matches_found:
            parts.append("Lists " + ", ".join(diet_matches_found).lower() + " dietary options")
        if amenities_found:
            parts.append("Lists " + ", ".join(amenities_found))

        explanation = ". ".join(parts) + "."
        if category == "restaurants" and diet_matches_found:
            explanation += " Confirm dietary needs directly with the restaurant."
        if category == "restaurants":
            missing = [v for v in selected_diet if v not in diet_matches_found]
            if missing:
                explanation += " Unverified dietary requirements: " + ", ".join(missing) + "."
        elif category == "accommodation":
            missing = [v for v in selected_amenities if v not in amenities_found]
            if missing:
                explanation += " Other requested amenities are unverified."
        if feedback_score > 0:
            explanation += " Boosted by your feedback."
        elif feedback_score < 0:
            explanation += " Lowered by your feedback."
        place["why"] = explanation
        ranked.append(place)
    ranked.sort(key=lambda p: (p["diet_priority"], p["match_score"]), reverse=True)
    return ranked
