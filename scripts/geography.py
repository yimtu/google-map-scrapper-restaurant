"""Assign reusable geographic layers to normalized FoodScan places."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .territory import geometry_contains

UNKNOWN_MUNICIPALITY = "UNKNOWN"
GEOGRAPHY_FIELDS = (
    "municipality",
    "inside_core_periferico",
    "inside_urban_amg",
    "inside_amg_full",
    "geography_source",
    "geography_verified_at",
)


def _valid_coordinate(value, minimum, maximum):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and minimum <= value <= maximum)


def _sources(features):
    values = []
    for feature in features:
        properties = feature.get("properties") or {}
        source = properties.get("source_name") or properties.get("source")
        if source and source not in values:
            values.append(str(source))
    return values


class GeographyIndex:
    """Immutable index over approved territory layers.

    Missing operational layers remain unknown. This deliberately distinguishes an
    unavailable polygon from a verified point outside an available polygon.
    """

    def __init__(self, territory):
        features = tuple(territory.get("features") or ())
        self.municipal_features = tuple(
            feature for feature in features
            if (feature.get("properties") or {}).get("scope") == "AMG_FULL"
            and (feature.get("properties") or {}).get("municipality")
            and (feature.get("properties") or {}).get("approved") is True
        )
        self.amg_features = tuple(
            feature for feature in features
            if (feature.get("properties") or {}).get("scope") == "AMG_FULL"
            and (feature.get("properties") or {}).get("approved") is True
        )
        self.core_features = self._approved(features, "CORE_PERIFERICO")
        self.urban_features = self._approved(features, "URBAN_AMG")
        has_core = any((f.get("properties") or {}).get("scope") == "CORE_PERIFERICO" for f in features)
        has_urban = any((f.get("properties") or {}).get("scope") == "URBAN_AMG" for f in features)
        self.layer_status = {
            "CORE_PERIFERICO": "approved" if self.core_features else "unapproved",
            "URBAN_AMG": "approved" if self.urban_features else ("unapproved" if has_urban else "pending_source"),
            "AMG_FULL": "approved" if self.amg_features else "unapproved",
        }
        self.geography_source = _sources(
            self.municipal_features + self.core_features + self.urban_features
        )

    @staticmethod
    def _approved(features, scope):
        return tuple(
            feature for feature in features
            if (feature.get("properties") or {}).get("scope") == scope
            and (feature.get("properties") or {}).get("approved") is True
        )

    @staticmethod
    def _inside(features, latitude, longitude):
        return any(geometry_contains(feature["geometry"], latitude, longitude) for feature in features)

    def assign(self, place, verified_at=None):
        """Return a new place dictionary containing all geographic attributes."""
        latitude, longitude = place.get("latitude"), place.get("longitude")
        valid = (_valid_coordinate(latitude, -90, 90)
                 and _valid_coordinate(longitude, -180, 180))
        matches = [] if not valid else [
            feature for feature in self.municipal_features
            if geometry_contains(feature["geometry"], latitude, longitude)
        ]
        municipality = ((matches[0].get("properties") or {}).get("municipality")
                        if len(matches) == 1 else UNKNOWN_MUNICIPALITY)
        timestamp = verified_at or datetime.now(timezone.utc).isoformat()
        return {
            **place,
            "municipality": municipality or UNKNOWN_MUNICIPALITY,
            "inside_core_periferico": (self._inside(self.core_features, latitude, longitude)
                                        if valid and self.core_features else None),
            "inside_urban_amg": (self._inside(self.urban_features, latitude, longitude)
                                  if valid and self.urban_features else None),
            "inside_amg_full": self._inside(self.amg_features, latitude, longitude) if valid else False,
            "geography_source": list(self.geography_source),
            "geography_verified_at": timestamp,
        }

    def assign_many(self, places, verified_at=None):
        timestamp = verified_at or datetime.now(timezone.utc).isoformat()
        return [self.assign(place, timestamp) for place in places]
