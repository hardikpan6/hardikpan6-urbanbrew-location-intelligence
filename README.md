# UrbanBrew Next Store Location Intelligence

## Problem Statement

UrbanBrew Coffee plans to open its next store in Jaipur. This project builds a **data-driven location intelligence system** that evaluates 15 candidate locations using spatial, competitive, commercial, and accessibility data.

**One-line problem:** "How can UrbanBrew use spatial, competitive, commercial, and accessibility data to systematically evaluate potential locations for its next store in Jaipur?"

## Architecture

```
CSV Datasets (realistic Jaipur data)
  → Snowflake RAW schema (6 tables)
    → ANALYTICS schema (Haversine UDF + 6 scoring views + final scorecard)
      → Streamlit Dashboard (interactive comparison + map)
```

## Scoring Methodology

Each candidate location receives six sub-scores (0-100, min-max normalized):

| Sub-Score | What It Measures | Data Source | Radius |
|-----------|-----------------|-------------|--------|
| **Competition Score** | Fewer nearby cafes/restaurants = higher opportunity | competitor_cafes | 1.0 km |
| **Accessibility Score** | Closer to operational metro station = higher score | metro_stations | All |
| **Commercial Activity Score** | Weighted count of POIs (offices, malls, education, etc.) | commercial_pois | 1.5 km |
| **Purchasing Power Benchmark** | H14 Census asset index (car + computer ownership proxy) | household_assets_2011 | Area-level |
| **Demand Proxy** | Composite: 65% commercial activity + 35% accessibility | Derived | — |
| **Cannibalization Score** | Farther from existing UrbanBrew = lower risk = higher score | existing_stores | All |

### POI Category Weights (Commercial Activity)

| Category | Weight | Rationale |
|----------|--------|-----------|
| Office/IT | 2.0 | Primary coffee consumers (working professionals) |
| Retail/Mall | 1.8 | High footfall, impulse purchases |
| Hospitality | 1.5 | Tourist/visitor traffic |
| Transport | 1.5 | Transit hubs generate walk-in traffic |
| Entertainment | 1.3 | Leisure visitors |
| Education | 1.2 | Student demographic |
| Tourism | 1.0 | Seasonal but relevant |
| Healthcare | 0.8 | Visitors/staff, lower coffee correlation |

### Composite Opportunity Score

```
Score = 0.20 × Competition + 0.15 × Accessibility + 0.25 × Commercial Activity
      + 0.15 × Purchasing Power + 0.15 × Demand Proxy + 0.10 × Cannibalization
```

Weights are adjustable via dashboard sliders.

| Grade | Score Range | Meaning |
|-------|-------------|---------|
| A | >= 70 | Strong Opportunity |
| B | 50-69 | Moderate Opportunity |
| C | 30-49 | Needs Investigation |
| D | < 30 | Low Priority |

## Data Dictionary

### RAW.CANDIDATE_LOCATIONS (15 rows)
| Column | Type | Description |
|--------|------|-------------|
| LOCATION_ID | VARCHAR | Unique ID (LOC01-LOC15) |
| LOCATION_NAME | VARCHAR | Descriptive name |
| AREA | VARCHAR | Jaipur area/neighborhood |
| LAT, LON | FLOAT | Geographic coordinates |
| ZONE_TYPE | VARCHAR | Commercial classification |
| AVG_RENT_PER_SQFT | INT | Estimated rent benchmark (INR) |
| FOOTFALL_ESTIMATE_CATEGORY | VARCHAR | High/Medium/Low |

### RAW.COMPETITOR_CAFES (55 rows)
Cafes, QSRs, and restaurants across Jaipur with type, rating, and price range.

### RAW.METRO_STATIONS (18 rows)
Jaipur Metro Pink Line (operational) + Yellow Line (planned/under construction).

### RAW.COMMERCIAL_POIS (85 rows)
Points of interest: Education, Healthcare, Hospitality, Office-IT, Retail-Mall, Entertainment, Tourism, Transport.

### RAW.EXISTING_STORES (4 rows)
Current UrbanBrew locations in Jaipur.

### RAW.HOUSEHOLD_ASSETS (15 rows)
2011 Census H14 data at area level: vehicle ownership, computer ownership, asset index.

## Important Limitations

1. **Purchasing Power is a historical benchmark** — The H14 asset index comes from the 2011 Census. It does NOT represent current household income. It should be interpreted as a relative affluence proxy, not an absolute measure.

2. **No actual footfall or revenue data** — Demand is inferred from commercial activity density and transit accessibility. These are proxies, not direct measurements.

3. **Simulated data** — The datasets are generated based on real Jaipur geography (actual coordinates, real area names, real metro stations) but competitor counts, ratings, and household percentages are approximated.

4. **Static analysis** — No time-series component. Real-world location decisions would also consider seasonal patterns, planned development, and population growth trends.

5. **Distance-based only** — Uses Haversine (straight-line) distance, not road network distance.

## Running the Dashboard

### Prerequisites
- Python 3.9+
- Snowflake account with data loaded (run `sql/setup.sql`)
- Snowflake connection configured

### Local Run
```bash
pip install streamlit plotly pandas snowflake-snowpark-python
SNOWFLAKE_DEFAULT_CONNECTION_NAME=<your-connection> streamlit run streamlit_app.py
```

### Power BI Connection (Optional)
Connect Power BI to `URBANBREW_LOCATION_INTEL.ANALYTICS.LOCATION_SCORECARD` view using the Snowflake connector. All sub-scores and the composite Opportunity Score are available as columns.

## Project Structure

```
snowflake project/
├── data/                        # CSV source files
│   ├── candidate_locations.csv
│   ├── competitor_cafes.csv
│   ├── metro_stations.csv
│   ├── commercial_pois.csv
│   ├── existing_stores.csv
│   └── household_assets_2011.csv
├── sql/
│   └── setup.sql               # Full Snowflake DDL/DML script
├── streamlit_app.py            # Dashboard application
├── pyproject.toml              # Python dependencies
└── README.md                   # This file
```
