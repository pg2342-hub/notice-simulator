"""Customer segments the panel simulates. Each matches a row the SHED report publishes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    id: str
    label: str
    who: str


SEGMENTS: list[Segment] = [
    Segment("inc_lt25", "Income under $25K", "US adults whose family income is under $25,000 a year, any age"),
    Segment("inc_25_50", "Income $25K to $50K", "US adults whose family income is $25,000 to $49,999 a year, any age"),
    Segment(
        "inc_50_100", "Income $50K to $100K", "US adults whose family income is $50,000 to $99,999 a year, any age"
    ),
    Segment("inc_100p", "Income $100K or more", "US adults whose family income is $100,000 a year or more, any age"),
    Segment("age_18_29", "Age 18 to 29", "US adults aged 18 to 29, any income"),
    Segment("age_30_44", "Age 30 to 44", "US adults aged 30 to 44, any income"),
    Segment("age_45_59", "Age 45 to 59", "US adults aged 45 to 59, any income"),
    Segment("age_60p", "Age 60 or older", "US adults aged 60 or older, any income"),
]

BY_ID = {s.id: s for s in SEGMENTS}
