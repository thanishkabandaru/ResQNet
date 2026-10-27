"""Official Indian Government Open Government Data (OGD) integration and provenance.

Sources:
- National Crime Records Bureau (NCRB), Ministry of Home Affairs:
  Accidental Deaths & Suicides in India (ADSI) - 2023 / 2024
  Resource: State/UT/City-wise Number of Cases Reported and Persons Injured and Died due to Traffic Accidents
- Ministry of Road Transport and Highways (MoRTH):
  Total Number of Road Accidents in India
"""

import csv
import io
import math
from pathlib import Path
import sqlite3
import urllib.request
import ssl

from database import get_db_connection

OFFICIAL_DATA_DIR = Path(__file__).resolve().parent / "official_government_data"
DEFAULT_NCRB_CSV_PATH = OFFICIAL_DATA_DIR / "NCRB_ADSI_2023_Table_1A.2_2.csv"

NCRB_PROVENANCE = {
    "source_name": "National Crime Records Bureau (NCRB)",
    "department": "Ministry of Home Affairs",
    "dataset_title": (
        "Accidental Deaths & Suicides in India (ADSI) - "
        "State/UT/City-wise Number of Cases Reported and Persons Injured and Died due to Traffic Accidents"
    ),
    "dataset_year": 2023,
    "published_year": "2023 (Latest published official table on OGD)",
    "geographic_granularity": "State, Union Territory, and 53 Mega Cities (including Andhra Pradesh, Vijayawada, and Visakhapatnam)",
    "time_granularity": "Annual",
    "file_format": "CSV",
    "source_catalog_url": (
        "https://ap.data.gov.in/resource/"
        "stateutcity-wise-number-cases-reported-and-persons-injured-and-died-due-traffic-accidents"
    ),
    "dataset_file_url": (
        "https://www.data.gov.in/files/ogdpv2dms/s3fs-public/NCRB_ADSI_2023_Table_1A.2_2.csv"
    ),
    "license": "Government Open Data License - India (GODL-India)",
}

MORTH_PROVENANCE = {
    "source_name": "Ministry of Road Transport and Highways (MoRTH)",
    "department": "Ministry of Road Transport and Highways",
    "dataset_title": "Total Number of Road Accidents in India",
    "source_catalog_url": "https://data.gov.in/catalog/total-number-road-accidents-india",
    "api_url": "https://api.data.gov.in/resource/9709bed2-7ac4-43b2-87d9-05f01910b07b",
    "status": "Official resource documented; direct API requires registered OGD API key",
    "message": (
        "The MoRTH catalog Total Number of Road Accidents in India is officially registered on data.gov.in. "
        "The live REST API endpoint requires a registered OGD API key per government access policy. "
        "Verified official NCRB ADSI statistical data is actively imported."
    ),
    "license": "Government Open Data License - India (GODL-India)",
}

CITY_STATE_MAPPING = {
    "Agra": "Uttar Pradesh",
    "Ahmedabad": "Gujarat",
    "Amritsar": "Punjab",
    "Asansol": "West Bengal",
    "Aurangabad": "Maharashtra",
    "Bengaluru": "Karnataka",
    "Bhopal": "Madhya Pradesh",
    "Chandigarh (City)": "Chandigarh",
    "Chennai": "Tamil Nadu",
    "Coimbatore": "Tamil Nadu",
    "Delhi (City)": "Delhi",
    "Dhanbad": "Jharkhand",
    "Durg Bhilainagar": "Chhattisgarh",
    "Faridabad": "Haryana",
    "Ghaziabad": "Uttar Pradesh",
    "Gwalior": "Madhya Pradesh",
    "Hyderabad": "Telangana",
    "Indore": "Madhya Pradesh",
    "Jabalpur": "Madhya Pradesh",
    "Jaipur": "Rajasthan",
    "Jamshedpur": "Jharkhand",
    "Jodhpur": "Rajasthan",
    "Kannur": "Kerala",
    "Kanpur": "Uttar Pradesh",
    "Kochi": "Kerala",
    "Kolkata": "West Bengal",
    "Kollam": "Kerala",
    "Kota": "Rajasthan",
    "Kozhikode": "Kerala",
    "Lucknow": "Uttar Pradesh",
    "Ludhiana": "Punjab",
    "Madurai": "Tamil Nadu",
    "Malappuram": "Kerala",
    "Meerut": "Uttar Pradesh",
    "Mumbai": "Maharashtra",
    "Nagpur": "Maharashtra",
    "Nasik": "Maharashtra",
    "Patna": "Bihar",
    "Prayagraj": "Uttar Pradesh",
    "Pune": "Maharashtra",
    "Raipur": "Chhattisgarh",
    "Rajkot": "Gujarat",
    "Ranchi": "Jharkhand",
    "Srinagar": "Jammu and Kashmir",
    "Surat": "Gujarat",
    "Thiruvananthapuram": "Kerala",
    "Thrissur": "Kerala",
    "Tiruchirappalli": "Tamil Nadu",
    "Vadodara": "Gujarat",
    "Varanasi": "Uttar Pradesh",
    "Vasai Virar": "Maharashtra",
    "Vijayawada": "Andhra Pradesh",
    "Vishakhapatnam": "Andhra Pradesh",
}

EXPECTED_COLUMNS = {
    "Sl. No.",
    "State/Ut/",
    "Road Accidents - Cases",
    "Road Accidents - Injured",
    "Road Accidents - Died",
    "Railway Accidents - Cases",
    "Railway Accidents - Injured",
    "Railway Accidents - Died",
    "Railway Crossing Accidents - Cases",
    "Railway Crossing Accidents - Injured",
    "Railway Crossing Accidents - Died",
    "Total Traffic Accidents - Cases",
    "Total Traffic Accidents - Injured",
    "Total Traffic Accidents - Died",
}

METRIC_MAPPINGS = [
    ("Road Accidents", "Cases Reported", "Road Accidents - Cases"),
    ("Road Accidents", "Persons Injured", "Road Accidents - Injured"),
    ("Road Accidents", "Persons Died", "Road Accidents - Died"),
    ("Railway Accidents", "Cases Reported", "Railway Accidents - Cases"),
    ("Railway Accidents", "Persons Injured", "Railway Accidents - Injured"),
    ("Railway Accidents", "Persons Died", "Railway Accidents - Died"),
    ("Railway Crossing Accidents", "Cases Reported", "Railway Crossing Accidents - Cases"),
    ("Railway Crossing Accidents", "Persons Injured", "Railway Crossing Accidents - Injured"),
    ("Railway Crossing Accidents", "Persons Died", "Railway Crossing Accidents - Died"),
    ("Total Traffic Accidents", "Cases Reported", "Total Traffic Accidents - Cases"),
    ("Total Traffic Accidents", "Persons Injured", "Total Traffic Accidents - Injured"),
    ("Total Traffic Accidents", "Persons Died", "Total Traffic Accidents - Died"),
]


def validate_and_parse_ncrb_csv(csv_content: str):
    """Validate official NCRB ADSI CSV content and return parsed records.
    
    Raises ValueError if required columns are missing, numeric fields are negative,
    or rows are malformed.
    """
    reader = csv.DictReader(io.StringIO(csv_content.strip()))
    if not reader.fieldnames:
        raise ValueError("CSV file has no headers.")

    field_set = set(reader.fieldnames)
    missing = EXPECTED_COLUMNS - field_set
    if missing:
        raise ValueError(f"Missing required columns in official CSV: {missing}")

    records = []
    for row_idx, row in enumerate(reader, start=1):
        raw_name = (row.get("State/Ut/") or "").strip()
        sl_no_raw = (row.get("Sl. No.") or "").strip()

        if not raw_name:
            continue

        # Classify geographic level
        if raw_name.startswith("Total (States)"):
            geo_level = "All States Combined"
            state = "All States"
            city = None
        elif raw_name.startswith("Total (UTs)"):
            geo_level = "All UTs Combined"
            state = "All UTs"
            city = None
        elif raw_name.startswith("Total (Cities)"):
            geo_level = "All Mega Cities Combined"
            state = "All Mega Cities"
            city = None
        elif raw_name.startswith("Total (All India)"):
            geo_level = "National"
            state = "India"
            city = None
        elif sl_no_raw.isdigit():
            sl_no = int(sl_no_raw)
            if 1 <= sl_no <= 28:
                geo_level = "State"
                state = raw_name
                city = None
            elif 29 <= sl_no <= 36:
                geo_level = "Union Territory"
                state = raw_name
                city = None
            elif 37 <= sl_no <= 89:
                geo_level = "City"
                city = raw_name
                state = CITY_STATE_MAPPING.get(raw_name, "Unknown")
            else:
                geo_level = "Other"
                state = raw_name
                city = None
        else:
            geo_level = "Other"
            state = raw_name
            city = None

        for category, metric, col_name in METRIC_MAPPINGS:
            val_str = (row.get(col_name) or "").strip().replace(",", "")
            try:
                numeric_val = float(val_str) if "." in val_str else int(val_str)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Row {row_idx} ({raw_name}) column '{col_name}' has non-numeric value: '{val_str}'"
                )

            if numeric_val < 0:
                raise ValueError(
                    f"Row {row_idx} ({raw_name}) column '{col_name}' has negative count: {numeric_val}"
                )

            # Deterministic unique identifier for duplicate protection
            norm_state = (state or "").replace(" ", "_")
            norm_city = (city or "").replace(" ", "_")
            norm_cat = category.replace(" ", "_")
            norm_metric = metric.replace(" ", "_")
            record_id = (
                f"NCRB_ADSI_2023_{geo_level.replace(' ', '_')}_"
                f"{norm_state}_{norm_city}_{norm_cat}_{norm_metric}"
            )

            records.append({
                "record_identifier": record_id,
                "source_name": NCRB_PROVENANCE["source_name"],
                "department": NCRB_PROVENANCE["department"],
                "dataset_title": NCRB_PROVENANCE["dataset_title"],
                "dataset_year": NCRB_PROVENANCE["dataset_year"],
                "state": state,
                "district": None,
                "city": city,
                "geographic_level": geo_level,
                "category": category,
                "metric": metric,
                "value": numeric_val,
                "unit": "count",
                "source_url": NCRB_PROVENANCE["dataset_file_url"],
                "license": NCRB_PROVENANCE["license"],
            })

    return records


def import_official_government_data(csv_path_or_url=None, connection=None):
    """Import official government records with validation and duplicate protection."""
    close_conn = False
    if connection is None:
        connection = get_db_connection()
        close_conn = True

    try:
        content = None
        path = Path(csv_path_or_url) if csv_path_or_url else DEFAULT_NCRB_CSV_PATH

        if path and path.is_file():
            content = path.read_text(encoding="utf-8", errors="ignore")
        elif isinstance(csv_path_or_url, str) and csv_path_or_url.startswith("http"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(csv_path_or_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
                content = res.read().decode("utf-8", errors="ignore")
        elif DEFAULT_NCRB_CSV_PATH.is_file():
            content = DEFAULT_NCRB_CSV_PATH.read_text(encoding="utf-8", errors="ignore")

        if not content:
            raise FileNotFoundError(
                f"Could not locate official government dataset at {csv_path_or_url or DEFAULT_NCRB_CSV_PATH}"
            )

        records = validate_and_parse_ncrb_csv(content)

        # Insert records with duplicate protection (record_identifier is UNIQUE)
        cursor = connection.cursor()
        inserted_count = 0
        for rec in records:
            cursor.execute(
                """
                INSERT OR IGNORE INTO government_historical_data (
                    record_identifier, source_name, department, dataset_title,
                    dataset_year, state, district, city, geographic_level,
                    category, metric, value, unit, source_url, license
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["record_identifier"],
                    rec["source_name"],
                    rec["department"],
                    rec["dataset_title"],
                    rec["dataset_year"],
                    rec["state"],
                    rec["district"],
                    rec["city"],
                    rec["geographic_level"],
                    rec["category"],
                    rec["metric"],
                    rec["value"],
                    rec["unit"],
                    rec["source_url"],
                    rec["license"],
                ),
            )
            if cursor.rowcount > 0:
                inserted_count += 1

        # Track in historical_dataset_imports
        cursor.execute(
            """
            INSERT INTO historical_dataset_imports (
                source, dataset_name, dataset_url, geographic_level,
                period_start, period_end, import_method, imported_record_count, import_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                NCRB_PROVENANCE["source_name"],
                NCRB_PROVENANCE["dataset_title"],
                NCRB_PROVENANCE["dataset_file_url"],
                NCRB_PROVENANCE["geographic_granularity"],
                "2023-01-01",
                "2023-12-31",
                "Official OGD CSV verified import",
                inserted_count,
                f"Parsed {len(records)} statistical data points across 93 State/UT/City entities.",
            ),
        )
        connection.commit()

        total_stored = cursor.execute(
            "SELECT COUNT(*) FROM government_historical_data"
        ).fetchone()[0]

        return {
            "status": "success",
            "imported_count": inserted_count,
            "total_stored": total_stored,
            "parsed_records": len(records),
            "provenance": NCRB_PROVENANCE,
            "secondary_source": MORTH_PROVENANCE,
        }
    finally:
        if close_conn:
            connection.close()


def get_government_data_summary(connection=None):
    """Retrieve structured official government intelligence for the UI."""
    close_conn = False
    if connection is None:
        connection = get_db_connection()
        close_conn = True

    try:
        total_rows = connection.execute(
            "SELECT COUNT(*) FROM government_historical_data"
        ).fetchone()[0]

        if total_rows == 0:
            return {
                "available": False,
                "message": "Official government data is not yet imported.",
                "provenance": NCRB_PROVENANCE,
                "secondary_source": MORTH_PROVENANCE,
            }

        # Query State Summary: Andhra Pradesh
        ap_rows = connection.execute(
            """
            SELECT category, metric, value FROM government_historical_data
            WHERE geographic_level = 'State' AND state = 'Andhra Pradesh'
            ORDER BY category, metric
            """
        ).fetchall()
        ap_stats = {f"{r['category']} - {r['metric']}": r["value"] for r in ap_rows}

        # Query Mega City Summaries (Vijayawada, Vishakhapatnam)
        cities_rows = connection.execute(
            """
            SELECT city, category, metric, value FROM government_historical_data
            WHERE geographic_level = 'City' AND city IN ('Vijayawada', 'Vishakhapatnam')
            ORDER BY city, category, metric
            """
        ).fetchall()
        city_stats = {}
        for r in cities_rows:
            city_stats.setdefault(r["city"], {})[f"{r['category']} - {r['metric']}"] = r["value"]

        # National Totals
        national_rows = connection.execute(
            """
            SELECT category, metric, value FROM government_historical_data
            WHERE geographic_level = 'National'
            ORDER BY category, metric
            """
        ).fetchall()
        national_stats = {f"{r['category']} - {r['metric']}": r["value"] for r in national_rows}

        # State Comparison List
        states_list = connection.execute(
            """
            SELECT state, 
                   MAX(CASE WHEN category = 'Road Accidents' AND metric = 'Cases Reported' THEN value ELSE 0 END) as road_cases,
                   MAX(CASE WHEN category = 'Road Accidents' AND metric = 'Persons Died' THEN value ELSE 0 END) as road_deaths,
                   MAX(CASE WHEN category = 'Road Accidents' AND metric = 'Persons Injured' THEN value ELSE 0 END) as road_injured,
                   MAX(CASE WHEN category = 'Total Traffic Accidents' AND metric = 'Cases Reported' THEN value ELSE 0 END) as total_traffic_cases
            FROM government_historical_data
            WHERE geographic_level = 'State'
            GROUP BY state
            ORDER BY road_cases DESC
            """
        ).fetchall()

        # Mega Cities Comparison List
        cities_list = connection.execute(
            """
            SELECT city, state,
                   MAX(CASE WHEN category = 'Road Accidents' AND metric = 'Cases Reported' THEN value ELSE 0 END) as road_cases,
                   MAX(CASE WHEN category = 'Road Accidents' AND metric = 'Persons Died' THEN value ELSE 0 END) as road_deaths,
                   MAX(CASE WHEN category = 'Road Accidents' AND metric = 'Persons Injured' THEN value ELSE 0 END) as road_injured
            FROM government_historical_data
            WHERE geographic_level = 'City'
            GROUP BY city, state
            ORDER BY road_cases DESC
            """
        ).fetchall()

        latest_import = connection.execute(
            "SELECT MAX(imported_at) FROM government_historical_data"
        ).fetchone()[0]

        return {
            "available": True,
            "source": NCRB_PROVENANCE["source_name"],
            "department": NCRB_PROVENANCE["department"],
            "dataset_title": NCRB_PROVENANCE["dataset_title"],
            "year": NCRB_PROVENANCE["dataset_year"],
            "geographic_granularity": NCRB_PROVENANCE["geographic_granularity"],
            "license": NCRB_PROVENANCE["license"],
            "source_url": NCRB_PROVENANCE["dataset_file_url"],
            "source_catalog_url": NCRB_PROVENANCE["source_catalog_url"],
            "imported_at": latest_import,
            "total_records": total_rows,
            "andhra_pradesh": {
                "state": "Andhra Pradesh",
                "road_accident_cases": ap_stats.get("Road Accidents - Cases Reported", 0),
                "road_accident_deaths": ap_stats.get("Road Accidents - Persons Died", 0),
                "road_accident_injured": ap_stats.get("Road Accidents - Persons Injured", 0),
                "railway_accident_cases": ap_stats.get("Railway Accidents - Cases Reported", 0),
                "railway_accident_deaths": ap_stats.get("Railway Accidents - Persons Died", 0),
                "total_traffic_cases": ap_stats.get("Total Traffic Accidents - Cases Reported", 0),
                "total_traffic_deaths": ap_stats.get("Total Traffic Accidents - Persons Died", 0),
            },
            "cities": {
                "Vijayawada": {
                    "city": "Vijayawada",
                    "state": "Andhra Pradesh",
                    "road_accident_cases": city_stats.get("Vijayawada", {}).get("Road Accidents - Cases Reported", 0),
                    "road_accident_deaths": city_stats.get("Vijayawada", {}).get("Road Accidents - Persons Died", 0),
                    "road_accident_injured": city_stats.get("Vijayawada", {}).get("Road Accidents - Persons Injured", 0),
                },
                "Vishakhapatnam": {
                    "city": "Vishakhapatnam",
                    "state": "Andhra Pradesh",
                    "road_accident_cases": city_stats.get("Vishakhapatnam", {}).get("Road Accidents - Cases Reported", 0),
                    "road_accident_deaths": city_stats.get("Vishakhapatnam", {}).get("Road Accidents - Persons Died", 0),
                    "road_accident_injured": city_stats.get("Vishakhapatnam", {}).get("Road Accidents - Persons Injured", 0),
                },
            },
            "national_totals": {
                "road_accident_cases": national_stats.get("Road Accidents - Cases Reported", 0),
                "road_accident_deaths": national_stats.get("Road Accidents - Persons Died", 0),
                "road_accident_injured": national_stats.get("Road Accidents - Persons Injured", 0),
                "total_traffic_cases": national_stats.get("Total Traffic Accidents - Cases Reported", 0),
                "total_traffic_deaths": national_stats.get("Total Traffic Accidents - Persons Died", 0),
            },
            "states_summary": [dict(r) for r in states_list],
            "cities_summary": [dict(r) for r in cities_list],
            "secondary_source": MORTH_PROVENANCE,
            "disclaimer": (
                "Government statistics are official historical records published by NCRB/MoRTH at their published "
                "geographic levels (State, Union Territory, and City). They provide macro-level historical context "
                "and should not be interpreted as local incident counts for small spatial radii (e.g., 1-km radius)."
            ),
        }
    finally:
        if close_conn:
            connection.close()


def query_government_records(
    connection=None,
    geographic_level=None,
    state=None,
    city=None,
    category=None,
    limit=100,
):
    """Query government records with optional filters."""
    close_conn = False
    if connection is None:
        connection = get_db_connection()
        close_conn = True

    try:
        conditions = []
        params = []
        if geographic_level:
            conditions.append("geographic_level = ?")
            params.append(geographic_level)
        if state:
            conditions.append("state = ?")
            params.append(state)
        if city:
            conditions.append("city = ?")
            params.append(city)
        if category:
            conditions.append("category = ?")
            params.append(category)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT id, source_name, department, dataset_title, dataset_year,
                   state, district, city, geographic_level, category, metric,
                   value, unit, source_url, license, imported_at
            FROM government_historical_data
            {where_clause}
            ORDER BY id ASC
            LIMIT ?
        """
        params.append(limit)
        rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        if close_conn:
            connection.close()
