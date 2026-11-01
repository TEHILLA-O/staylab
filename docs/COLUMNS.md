# Inside Airbnb London: columns used by StayLab

Snapshot: **19 June 2026**. Source files stay untouched under `data/raw/london/`.

The public dataset describes listings and calendars. It does **not** contain
randomised experiment assignments or booking-funnel events. Those are generated
separately and labelled as simulated.

## `listings.csv.gz` (detailed listings)

| Column | Role in StayLab |
| --- | --- |
| `id` | Listing primary key (`listing_id`) |
| `host_id` | Host identifier |
| `host_is_superhost` | Superhost flag; raises baseline conversion |
| `neighbourhood_cleansed` | Borough used for segmentation and relative price |
| `latitude`, `longitude` | Marketplace geography (stored, not used in the test) |
| `property_type` | Host-declared property type |
| `room_type` | Entire home / private / hotel / shared, conversion covariate |
| `accommodates` | Capacity; used for guests and price-per-person |
| `bedrooms`, `beds` | Listing size |
| `price` | Advertised nightly rate (string like `$164.00`) |
| `minimum_nights`, `maximum_nights` | Stay constraints |
| `has_availability`, `availability_365` | Forward inventory filter |
| `number_of_reviews`, `number_of_reviews_ltm` | Social proof / exposure weight |
| `reviews_per_month` | Demand proxy for listing exposure |
| `review_scores_rating` | Quality signal (NULL if never reviewed) |
| `review_scores_value`, `review_scores_location` | Stored for context |
| `instant_bookable` | Marketplace attribute, **not** an experiment arm |
| `estimated_occupancy_l365d` | Occupancy context |
| `last_review` | Recency of reviews |

Derived in ETL (not in the raw file):

- `price_per_person`
- `neighbourhood_median_price`
- `price_vs_neighbourhood`
- `has_review_score`
- `calendar_availability_rate`, `calendar_avg_price`, `calendar_min_nights`

## `calendar.csv.gz`

| Column | Role |
| --- | --- |
| `listing_id` | Join key |
| `date` | Forward night |
| `available` | `t` / `f`: used for 180-day availability rate |
| `minimum_nights` | Stay rule actually in force |

The June 2026 snapshot does not publish a per-night `price` on the calendar.
Nightly rates therefore come from the listings file.

## `neighbourhoods.csv`

Borough names used as a geo filter / reference list.

## What is *not* in Inside Airbnb

- User ids
- Session ids
- Variant assignment
- Funnel events (`listing_view`, `cta_click`, …)
- Bookings, cancellations, revenue

Those live only in the simulated experiment tables.
