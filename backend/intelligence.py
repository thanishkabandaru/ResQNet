"""Transparent analytics over authorized ResQNet incident records."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import math

from sklearn.cluster import DBSCAN


CATEGORY_LABELS = (
    "Medical Emergency",
    "Accident",
    "Fire",
    "Road Hazard",
    "Crime",
    "Theft",
    "Missing Person",
    "Natural Disaster",
    "Building Collapse",
    "Electrical Emergency",
    "Gas Leak",
    "Other Emergency",
)
PRIORITY_LABELS = ("High", "Medium", "Low")
STATUS_LABELS = ("Received", "Assigned", "In Progress", "Resolved")
EARTH_RADIUS_KM = 6371.0088
IST = timezone(timedelta(hours=5, minutes=30))
# A concentration requires three incidents in one rolling window, not a single event.
SHORT_TERM_WINDOW_HOURS = 24
MIN_SHORT_TERM_INCIDENTS = 3
EXTREME_PROXIMITY_KM = 0.05
MIN_RECURRING_INCIDENTS = 3
MIN_RECURRING_DISTINCT_DATES = 3
HISTORICAL_DATA_NOTICE = {
    "label": "Government Historical Data",
    "available": False,
    "import_status": "not_imported",
    "source": "Open Government Data (OGD) Platform India",
    "publisher": "National Crime Records Bureau (NCRB), Ministry of Home Affairs",
    "dataset_name": (
        "State/UT/City-wise Number of Cases Reported and Persons Injured and Died "
        "due to Traffic Accidents during 2023"
    ),
    "year": 2023,
    "source_catalog_url": (
        "https://ap.data.gov.in/resource/"
        "stateutcity-wise-number-cases-reported-and-persons-injured-and-died-due-traffic-accidents"
    ),
    "dataset_file_url": (
        "https://www.data.gov.in/files/ogdpv2dms/s3fs-public/"
        "NCRB_ADSI_2023_Table_1A.2_2.csv"
    ),
    "dataset_file_size_bytes": 5644,
    "resource_id": "604263040",
    "resource_uuid": "1277ace4-acf7-4754-ae39-316cfc07d168",
    "api_url": (
        "https://api.data.gov.in/resource/"
        "1277ace4-acf7-4754-ae39-316cfc07d168?format=json&limit=1"
    ),
    "additional_source_catalog_url": (
        "https://delhi.data.gov.in/resource/"
        "stateutcity-wise-and-month-occurrence-wise-number-traffic-accidents-during-2023"
    ),
    "message": (
        "The official OGD record lists a 5,644-byte CSV, but its download returned "
        "HTTP 403 in this environment. The OGD resource API request without an API "
        "key returned HTTP 400. The official Delhi monthly resource could not be "
        "reached here due to a transport-level DNS/connection/TLS failure. No "
        "government rows have been imported; current intelligence is based only on "
        "ResQNet reports."
    ),
    "response_outcome": (
        "Government historical data is not imported; response outcomes are calculated "
        "only from ResQNet reports."
    ),
    "datasets": [],
}

PREVENTION_SUGGESTIONS = {
    "Accident": (
        "Review road conditions",
        "Review lighting and signage",
        "Consider monitoring during affected periods",
    ),
    "Fire": (
        "Review fire-safety conditions",
        "Review emergency access",
        "Consider a safety inspection",
    ),
    "Road Hazard": (
        "Consider a road-condition inspection",
        "Consider a maintenance review",
    ),
    "Crime": ("Review local safety measures", "Consider monitoring affected periods"),
    "Electrical Emergency": ("Consider an infrastructure inspection",),
    "Gas Leak": ("Consider an infrastructure and safety inspection",),
}


def parse_utc(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def haversine_km(latitude, longitude, other_latitude, other_longitude):
    radians = math.radians
    latitude_delta = radians(other_latitude - latitude)
    longitude_delta = radians(other_longitude - longitude)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(radians(latitude))
        * math.cos(radians(other_latitude))
        * math.sin(longitude_delta / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _resolution_minutes(report):
    created = parse_utc(report.get("created_at"))
    resolved = parse_utc(report.get("resolved_at"))
    if report.get("status") != "Resolved" or not created or not resolved:
        return None
    duration = (resolved - created).total_seconds() / 60
    return duration if duration >= 0 else None


def _average(values):
    return round(sum(values) / len(values), 1) if values else None


def _counter_data(rows, field, labels):
    counter = Counter(row.get(field) for row in rows)
    return [{"label": label, "count": counter.get(label, 0)} for label in labels]


def _monthly_trend(reports, now):
    monthly = []
    current_month = now.astimezone(IST).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for months_ago in range(11, -1, -1):
        month_index = current_month.month - 1 - months_ago
        year = current_month.year + month_index // 12
        month = month_index % 12 + 1
        monthly.append({"month": f"{year:04d}-{month:02d}", "count": 0})
    monthly_index = {item["month"]: item for item in monthly}
    for report in reports:
        created = parse_utc(report.get("created_at"))
        if created:
            month_key = created.astimezone(IST).strftime("%Y-%m")
            if month_key in monthly_index:
                monthly_index[month_key]["count"] += 1
    return monthly


def _general_intelligence(reports, similar_incidents, response_history, prevention, now):
    return {
        "available": True,
        "similar_incidents": similar_incidents,
        "trends": {
            "monthly": _monthly_trend(reports, now),
            "categories": _counter_data(reports, "emergency_type", CATEGORY_LABELS),
            "priorities": _counter_data(reports, "priority", PRIORITY_LABELS),
        },
        "response_history": response_history,
        "prevention": prevention,
    }


LOCAL_PROBLEM_LABELS = {
    "Road Hazard": "Possible recurring road hazard",
    "Accident": "Possible accident-prone pattern",
    "Fire": "Possible fire-related incident pattern",
    "Electrical Emergency": "Possible electrical safety concern",
    "Gas Leak": "Possible gas-related safety concern",
    "Crime": "Possible repeated crime pattern",
    "Theft": "Possible repeated theft pattern",
    "Medical Emergency": "Possible medical-emergency concentration",
    "Building Collapse": "Possible building safety concern",
    "Natural Disaster": "Possible natural-disaster concentration",
}

LOCATION_RECOMMENDATIONS = {
    "Road Hazard": (
        "Consider a road-safety assessment of the affected area, including road conditions, visibility, "
        "traffic movement, and recurring road obstructions or road-safety hazards."
    ),
    "Accident": (
        "Consider a road-safety assessment of the affected area, including road conditions, visibility, "
        "traffic movement, and recurring road-safety hazards."
    ),
    "Fire": (
        "Consider a fire-safety and electrical-safety assessment of the affected area, including potential "
        "ignition hazards and emergency access."
    ),
    "Electrical Emergency": (
        "Consider a fire-safety and electrical-safety assessment of the affected area, including potential "
        "ignition hazards, electrical infrastructure, and emergency access."
    ),
    "Gas Leak": (
        "Consider an infrastructure and safety assessment of the affected area, including potential "
        "ignition hazards, leak-prevention measures, and emergency access."
    ),
    "Crime": (
        "Consider increased safety monitoring and assessment of commonly affected locations and time periods."
    ),
    "Theft": (
        "Consider increased safety monitoring and assessment of commonly affected locations and time periods."
    ),
    "Medical Emergency": (
        "Consider reviewing emergency medical accessibility and response coverage for the affected area."
    ),
    "Building Collapse": (
        "Consider structural safety conditions and inspection of potentially unsafe structures in the affected area."
    ),
    "Natural Disaster": (
        "Consider reviewing local preparedness and relevant environmental risk factors based on the recorded incident pattern."
    ),
}


def _detect_short_term_concentration(area_reports, current_report_id):
    dated_reports = [
        (parse_utc(item.get("created_at")), item)
        for item in area_reports
    ]
    dated_reports = sorted(
        ((created, item) for created, item in dated_reports if created),
        key=lambda item: item[0],
    )
    left = 0
    best_window = []
    window = timedelta(hours=SHORT_TERM_WINDOW_HOURS)
    for right, (created, _) in enumerate(dated_reports):
        while created - dated_reports[left][0] > window:
            left += 1
        candidate_window = dated_reports[left:right + 1]
        if len(candidate_window) > len(best_window):
            best_window = candidate_window

    categories = sorted(
        {
            item.get("emergency_type")
            for _, item in best_window
            if item.get("emergency_type")
        }
    )
    historical_window = [
        (created, item)
        for created, item in best_window
        if item.get("id") != current_report_id
    ]
    historical_window_dates = sorted(
        {created.astimezone(IST).date().isoformat() for created, _ in historical_window}
    )
    incident_count = len(best_window)
    return {
        "detected": incident_count >= MIN_SHORT_TERM_INCIDENTS,
        "window_hours": SHORT_TERM_WINDOW_HOURS,
        "minimum_incidents": MIN_SHORT_TERM_INCIDENTS,
        "incident_count": incident_count,
        "previous_incident_count": sum(
            item.get("id") != current_report_id for _, item in best_window
        ),
        "mixed_categories": len(categories) > 1,
        "categories": categories,
        "previous_categories": sorted(
            {
                item.get("emergency_type")
                for _, item in historical_window
                if item.get("emergency_type")
            }
        ),
        "previous_category_counts": dict(
            Counter(
                item.get("emergency_type")
                for _, item in historical_window
                if item.get("emergency_type")
            )
        ),
        "previous_dates": historical_window_dates,
        "starts_at": best_window[0][0].isoformat() if best_window else None,
        "ends_at": best_window[-1][0].isoformat() if best_window else None,
    }


def _detect_recurring_pattern(earlier_reports):
    incidents_by_category = defaultdict(list)
    for item in earlier_reports:
        created = parse_utc(item.get("created_at"))
        category = item.get("emergency_type")
        if created and category:
            incidents_by_category[category].append((created.astimezone(IST).date(), item))

    candidates = []
    for category, incidents in incidents_by_category.items():
        dates = sorted({date for date, _ in incidents})
        if (
            len(incidents) >= MIN_RECURRING_INCIDENTS
            and len(dates) >= MIN_RECURRING_DISTINCT_DATES
        ):
            candidates.append((len(incidents), len(dates), category, dates))
    if not candidates:
        return {
            "detected": False,
            "category": None,
            "incident_count": 0,
            "distinct_dates": 0,
            "minimum_incidents": MIN_RECURRING_INCIDENTS,
            "minimum_distinct_dates": MIN_RECURRING_DISTINCT_DATES,
        }

    incident_count, distinct_dates, category, dates = max(
        candidates,
        key=lambda candidate: (
            candidate[1],
            candidate[0],
            candidate[2],
        ),
    )
    return {
        "detected": True,
        "category": category,
        "incident_count": incident_count,
        "distinct_dates": distinct_dates,
        "dates": [date.isoformat() for date in dates],
        "minimum_incidents": MIN_RECURRING_INCIDENTS,
        "minimum_distinct_dates": MIN_RECURRING_DISTINCT_DATES,
    }


def _location_assessment(report, earlier_reports, area_reports, radius_km, short_term):
    historical_count = len(earlier_reports)
    historical_dates = {
        created.astimezone(IST).date()
        for item in earlier_reports
        if (created := parse_utc(item.get("created_at")))
    }
    distinct_dates = len(historical_dates)
    category_counts = Counter(
        item.get("emergency_type")
        for item in earlier_reports
        if item.get("emergency_type")
    )
    dominant_category, dominant_count = (
        category_counts.most_common(1)[0] if category_counts else (None, 0)
    )
    high_priority_count = sum(item.get("priority") == "High" for item in earlier_reports)
    very_close = [
        item
        for item in earlier_reports
        if item["_distance_km"] <= EXTREME_PROXIMITY_KM
    ]
    recurring = _detect_recurring_pattern(earlier_reports)
    category_share = dominant_count / historical_count if historical_count else 0
    high_priority_share = high_priority_count / historical_count if historical_count else 0

    # Combine volume, date spread, proximity, category recurrence, and priority evidence.
    evidence_score = (
        int(historical_count >= 3)
        + int(historical_count >= 5)
        + int(distinct_dates >= 2)
        + int(distinct_dates >= 3)
        + int(bool(very_close))
        + int(dominant_count >= 2 and category_share >= 0.5)
        + (2 if recurring["detected"] else 0)
        + int(high_priority_count >= 2 and high_priority_share >= 0.5)
    )
    if (
        recurring["detected"]
        and historical_count >= 5
        and distinct_dates >= MIN_RECURRING_DISTINCT_DATES
        and evidence_score >= 5
    ):
        evidence_strength = "Strong"
    elif historical_count >= 3 and evidence_score >= 3:
        evidence_strength = "Moderate"
    else:
        evidence_strength = "Limited"

    date_detail = (
        f"across {distinct_dates} distinct dates"
        if distinct_dates > 1
        else "on the same date"
        if distinct_dates == 1
        else "with no valid historical timestamps"
    )
    evidence_explanation = (
        f"{evidence_strength} evidence: {historical_count} previous nearby "
        f"incident(s) {date_detail}; {len(very_close)} were within "
        f"{EXTREME_PROXIMITY_KM:.2f} km; {dominant_count} matched the most "
        f"common historical category"
        + (f" ({dominant_category})" if dominant_category else "")
        + f"; {high_priority_count} were high priority. "
        + (
            "A recurring category pattern across separate dates is present."
            if recurring["detected"]
            else "The records do not meet the separate-date recurrence threshold."
        )
    )

    def _map_observed_problem(category_name):
        if category_name in ("Accident", "Road Hazard"):
            return "Repeated road-safety incidents"
        if category_name in ("Fire", "Electrical Emergency", "Gas Leak"):
            return "Repeated fire-related incidents"
        if category_name in ("Crime", "Theft"):
            return "Repeated security-related incidents"
        if category_name == "Medical Emergency":
            return "Repeated medical emergencies"
        if category_name == "Natural Disaster":
            return "Repeated natural-disaster incidents"
        return f"Repeated {category_name.lower()} incidents"

    if recurring["detected"]:
        problem = LOCAL_PROBLEM_LABELS.get(
            recurring["category"],
            f"Possible recurring {recurring['category'].lower()} pattern",
        )
        observed_problem = _map_observed_problem(recurring["category"])
        problem_reason = (
            f"{recurring['incident_count']} previous {recurring['category']} incidents "
            f"occurred across {recurring['distinct_dates']} distinct dates within "
            f"{radius_km:g} km."
        )
        recommendation_category = recurring["category"]
    elif short_term["detected"] and short_term["mixed_categories"]:
        problem = "Possible recurring local safety/environmental issue"
        observed_problem = "High concentration of emergency incidents"
        problem_reason = (
            f"{short_term['incident_count']} incidents across "
            f"{len(short_term['categories'])} categories occurred within "
            f"{SHORT_TERM_WINDOW_HOURS} hours and {radius_km:g} km; the cause "
            "cannot be established from these records."
        )
        recommendation_category = None
    elif dominant_count >= 2 and category_share >= 0.5:
        problem = LOCAL_PROBLEM_LABELS.get(
            dominant_category,
            f"Possible {dominant_category.lower()} incident pattern",
        )
        observed_problem = _map_observed_problem(dominant_category)
        problem_reason = (
            f"{dominant_count} of {historical_count} previous nearby incidents were "
            f"categorized as {dominant_category} across {distinct_dates} distinct "
            f"date(s)."
        )
        recommendation_category = dominant_category
    elif short_term["detected"]:
        category = short_term["categories"][0] if short_term["categories"] else None
        problem = (
            LOCAL_PROBLEM_LABELS.get(category, f"Possible {category.lower()} pattern")
            if category
            else "Short-term incident concentration"
        )
        observed_problem = "High concentration of emergency incidents"
        problem_reason = (
            f"{short_term['incident_count']} incidents occurred within "
            f"{SHORT_TERM_WINDOW_HOURS} hours and {radius_km:g} km."
        )
        recommendation_category = category
    elif historical_count:
        problem = "Insufficient historical evidence"
        observed_problem = "Insufficient historical evidence"
        problem_reason = (
            f"{historical_count} previous nearby incident(s) are available, but no "
            "qualifying recurring or short-term pattern was detected."
        )
        recommendation_category = None
    else:
        problem = "Insufficient historical evidence"
        observed_problem = "Insufficient historical evidence"
        problem_reason = "No previous nearby ResQNet incidents were available for analysis."
        recommendation_category = None

    extreme_proximity = {
        "detected": bool(very_close),
        "threshold_km": EXTREME_PROXIMITY_KM,
        "count": len(very_close),
        "incidents": [
            {
                "id": item.get("id"),
                "category": item.get("emergency_type"),
                "date": item.get("created_at"),
                "distance_km": round(item["_distance_km"], 3),
            }
            for item in very_close
        ],
    }

    if recommendation_category:
        recommendation = LOCATION_RECOMMENDATIONS.get(
            recommendation_category,
            "Inspect the location for recurring hazards before applying long-term preventive measures.",
        )
    elif short_term["detected"]:
        recommendation = (
            "Investigate the location and consider a broader local safety assessment because "
            "multiple emergency categories have been recorded within the same area."
        )
    elif historical_count:
        recommendation = (
            "Review the available nearby incident records and inspect the location "
            "before selecting a long-term preventive measure."
        )
    else:
        recommendation = (
            "No location-specific preventive measure can be supported until nearby "
            "historical incident records are available."
        )

    farthest_close_km = max(
        (item["_distance_km"] for item in very_close),
        default=None,
    )
    if short_term["detected"] and short_term["mixed_categories"]:
        historical_window_categories = short_term["previous_category_counts"]
        category_summary = ", ".join(
            f"{category} ({count})"
            for category, count in sorted(historical_window_categories.items())
        )
        short_term_dates = short_term["previous_dates"]
        same_date_summary = (
            f"on {datetime.fromisoformat(short_term_dates[0]).strftime('%d %b %Y').lstrip('0')}"
            if len(short_term_dates) == 1
            else f"across {len(short_term_dates)} historical date(s)"
        )
        proximity_summary = (
            f"within approximately {farthest_close_km * 1000:.0f} metres"
            if farthest_close_km is not None
            else f"within the selected {radius_km:g} km radius"
        )
        recommendation_reason = (
            f"{short_term['previous_incident_count']} previous nearby incident(s) "
            f"({category_summary or 'category unavailable'}) occurred "
            f"{proximity_summary} of the current {report.get('emergency_type')} "
            f"report {same_date_summary}; mixed categories support inspection, not "
            "a specific cause."
        )
        if very_close:
            close_distances = ", ".join(
                f"{item['_distance_km'] * 1000:.0f} m" for item in very_close
            )
            recommendation_reason += (
                f" The recorded very-close distances were {close_distances}."
            )
    elif historical_count:
        recommendation_reason = (
            f"The recommendation follows {historical_count} previous nearby "
            f"incident(s) within {radius_km:g} km; the dominant recorded category "
            f"is {dominant_category or 'unavailable'}."
        )
    else:
        recommendation_reason = (
            "No previous nearby incident records support a more specific recommendation."
        )

    recommendation_basis = {
        "historical_incidents": historical_count,
        "area_incidents_including_current": len(area_reports),
        "very_close_incidents": len(very_close),
        "very_close_threshold_km": EXTREME_PROXIMITY_KM,
        "analysis_radius_km": radius_km,
        "dominant_historical_category": dominant_category,
        "dominant_historical_category_count": dominant_count,
        "distinct_historical_dates": distinct_dates,
        "high_priority_historical_incidents": high_priority_count,
        "recurring_pattern_detected": recurring["detected"],
        "short_term_concentration_detected": short_term["detected"],
        "evidence_strength": evidence_strength,
    }
    if not historical_count:
        data_limitation = (
            "No previous nearby records are available; no local pattern or cause can "
            "be established."
        )
    elif not recurring["detected"]:
        data_limitation = (
            f"Only {historical_count} previous nearby record(s) across {distinct_dates} "
            "distinct date(s) are available; a persistent long-term pattern requires "
            f"at least {MIN_RECURRING_INCIDENTS} incidents across "
            f"{MIN_RECURRING_DISTINCT_DATES} separate dates. Incident records alone "
            "cannot establish a cause."
        )
    else:
        data_limitation = (
            "A recurring pattern is visible in ResQNet records, but those records "
            "cannot establish its underlying cause or guarantee that a recommendation "
            "will prevent future incidents."
        )

    if short_term["detected"]:
        location_conclusion = (
            f"{len(area_reports)} incidents are recorded within the selected area, "
            "with a short-term concentration that warrants local inspection."
        )
    elif recurring["detected"]:
        location_conclusion = (
            f"Previous {recurring['category']} incidents recur across separate dates "
            "within the selected area."
        )
    elif historical_count:
        location_conclusion = (
            "Nearby incident records are available, but they do not establish a "
            "qualifying short-term or recurring location pattern."
        )
    else:
        location_conclusion = "Location-specific conclusion unavailable due to insufficient nearby records."

    return {
        "short_term_concentration": short_term,
        "extreme_proximity": extreme_proximity,
        "recurring_pattern": recurring,
        "evidence_strength": evidence_strength,
        "evidence_explanation": evidence_explanation,
        "observed_local_problem": observed_problem,
        "local_problem": problem,
        "local_problem_reason": problem_reason,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
        "recommendation_basis": recommendation_basis,
        "location_conclusion": location_conclusion,
        "conclusion_reason": recommendation_reason,
        "data_limitation": data_limitation,
    }


def _cluster_gps_reports(reports, radius_km=1.0, minimum_points=3):
    located = [
        report
        for report in reports
        if isinstance(report.get("latitude"), (int, float))
        and isinstance(report.get("longitude"), (int, float))
        and -90 <= report["latitude"] <= 90
        and -180 <= report["longitude"] <= 180
    ]
    if len(located) < minimum_points:
        return []

    coordinates = [
        [math.radians(report["latitude"]), math.radians(report["longitude"])]
        for report in located
    ]
    labels = DBSCAN(
        eps=radius_km / EARTH_RADIUS_KM,
        min_samples=minimum_points,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(coordinates)
    clusters = []
    for cluster_label in sorted(set(labels) - {-1}):
        members = [
            report
            for report, label in zip(located, labels)
            if label == cluster_label
        ]
        categories = Counter(report.get("emergency_type") for report in members)
        dominant_category = categories.most_common(1)[0][0]
        x = sum(math.cos(math.radians(report["latitude"])) * math.cos(math.radians(report["longitude"])) for report in members)
        y = sum(math.cos(math.radians(report["latitude"])) * math.sin(math.radians(report["longitude"])) for report in members)
        z = sum(math.sin(math.radians(report["latitude"])) for report in members)
        center_longitude = math.degrees(math.atan2(y, x))
        center_latitude = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
        repeat_count = sum(
            count for category, count in categories.items() if count >= minimum_points
        )
        clusters.append(
            {
                "incident_count": len(members),
                "dominant_category": dominant_category,
                "center": {
                    "latitude": round(center_latitude, 6),
                    "longitude": round(center_longitude, 6),
                },
                "repeat_count": repeat_count,
            }
        )
    return sorted(clusters, key=lambda cluster: cluster["incident_count"], reverse=True)


def _resolve_historical_data(db_connection=None):
    if db_connection is not None:
        try:
            from government_data import get_government_data_summary
            summary = get_government_data_summary(db_connection)
            if summary.get("available"):
                return summary
        except Exception:
            pass
    return HISTORICAL_DATA_NOTICE


def build_global_intelligence(reports, now=None, db_connection=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    daily_periods = Counter()
    recent = 0
    high_priority = 0
    resolved = 0
    resolution_values = []
    resolution_by_category = defaultdict(list)
    resolution_by_priority = defaultdict(list)
    resolution_by_department = defaultdict(list)

    for report in reports:
        created = parse_utc(report.get("created_at"))
        if created:
            if created >= cutoff:
                recent += 1
            hour = created.astimezone(IST).hour
            period = (
                "Overnight" if hour < 6 else
                "Morning" if hour < 12 else
                "Afternoon" if hour < 17 else
                "Evening" if hour < 21 else
                "Overnight"
            )
            daily_periods[period] += 1
        high_priority += report.get("priority") == "High"
        resolved += report.get("status") == "Resolved"
        duration = _resolution_minutes(report)
        if duration is not None:
            resolution_values.append(duration)
            resolution_by_category[report.get("emergency_type")].append(duration)
            resolution_by_priority[report.get("priority")].append(duration)
            if report.get("route_department"):
                resolution_by_department[report["route_department"]].append(duration)

    hotspots = _cluster_gps_reports(reports)
    repeat_incidents = sum(cluster["repeat_count"] for cluster in hotspots)
    official_data = _resolve_historical_data(db_connection)
    return {
        "source_labels": {
            "application": "ResQNet Records",
            "official": official_data.get("label", HISTORICAL_DATA_NOTICE["label"]),
        },
        "kpis": {
            "total_incidents": len(reports),
            "recent_incidents_30_days": recent,
            "high_priority_incidents": high_priority,
            "resolved_incidents": resolved,
            "repeat_incidents": repeat_incidents,
            "average_resolution_minutes": _average(resolution_values),
        },
        "categories": _counter_data(reports, "emergency_type", CATEGORY_LABELS),
        "priorities": _counter_data(reports, "priority", PRIORITY_LABELS),
        "statuses": _counter_data(reports, "status", STATUS_LABELS),
        "monthly_trend": _monthly_trend(reports, now),
        "time_period_pattern": [
            {"period": period, "count": daily_periods[period]}
            for period in ("Morning", "Afternoon", "Evening", "Overnight")
        ],
        "response_effectiveness": {
            "resolved_percentage": round(resolved * 100 / len(reports), 1) if reports else 0,
            "active_percentage": round((len(reports) - resolved) * 100 / len(reports), 1) if reports else 0,
            "average_resolution_minutes": _average(resolution_values),
            "resolution_by_category": [
                {"category": category, "average_minutes": _average(values)}
                for category, values in sorted(resolution_by_category.items())
            ],
            "resolution_by_priority": [
                {"priority": priority, "average_minutes": _average(values)}
                for priority, values in sorted(resolution_by_priority.items())
            ],
            "resolution_by_department": [
                {"department": department, "average_minutes": _average(values)}
                for department, values in sorted(resolution_by_department.items())
            ],
            "unavailable_message": "Resolution times are unavailable where resolution timestamps were not recorded.",
        },
        "hotspots": {
            "count": len(hotspots),
            "incident_count": sum(cluster["incident_count"] for cluster in hotspots),
            "clusters": hotspots,
            "minimum_points": 3,
            "radius_km": 1.0,
            "insufficient_data_message": "Insufficient data for hotspot detection.",
        },
        "future_risk_model": {
            "available": False,
            "message": "Future risk model requires additional historical records.",
        },
        "official_historical_data": official_data,
    }


def build_incident_intelligence(report, reports, radius_km=1.0, now=None, db_connection=None):
    if not isinstance(radius_km, (int, float)) or not 0.1 <= radius_km <= 50:
        raise ValueError("Analysis radius must be between 0.1 and 50 km")
    now = now or datetime.now(timezone.utc)
    official_data = _resolve_historical_data(db_connection)

    def _make_combined_evidence(count, rad):
        return {
            "local_resqnet_layer": {
                "title": "Local ResQNet Evidence",
                "incident_count": count,
                "radius_km": rad,
                "description": (
                    f"{count} emergency report(s) recorded within {rad:g} km in ResQNet."
                    if rad else "Location unavailable; no spatial radius calculated."
                ),
            },
            "government_historical_layer": {
                "title": "Government Historical Context",
                "available": official_data.get("available", False),
                "source": official_data.get("source"),
                "dataset_title": official_data.get("dataset_title"),
                "year": official_data.get("year"),
                "geographic_granularity": official_data.get("geographic_granularity"),
                "context_description": (
                    "Official government statistics (NCRB ADSI 2023) record 19,949 road accident cases for Andhra Pradesh "
                    "(1,522 in Vijayawada, 1,293 in Visakhapatnam, and 464,029 nationwide)."
                    if official_data.get("available")
                    else "Official government data is not yet imported."
                ),
                "disclaimer": (
                    "Government statistics are reported at their published geographic level (State, UT, and City) "
                    "and should not be interpreted as incident counts for this 1-km radius."
                ),
            },
        }
    has_location = (
        isinstance(report.get("latitude"), (int, float))
        and isinstance(report.get("longitude"), (int, float))
        and math.isfinite(report["latitude"])
        and math.isfinite(report["longitude"])
        and -90 <= report["latitude"] <= 90
        and -180 <= report["longitude"] <= 180
    )
    if not has_location:
        report_time = parse_utc(report.get("created_at"))
        similar_incidents = []
        category_count = 1
        for candidate in reports:
            if report.get("id") is not None and candidate.get("id") == report["id"]:
                continue
            category_match = candidate.get("emergency_type") == report.get("emergency_type")
            priority_match = candidate.get("priority") == report.get("priority")
            if not category_match and not priority_match:
                continue
            candidate_time = parse_utc(candidate.get("created_at"))
            if report_time and candidate_time and candidate_time > report_time:
                continue
            if category_match:
                category_count += 1
            similar_incidents.append(
                {
                    "id": candidate.get("id"),
                    "date": candidate.get("created_at"),
                    "category": candidate.get("emergency_type"),
                    "priority": candidate.get("priority"),
                    "distance_km": None,
                    "department": candidate.get("route_department"),
                    "destination": candidate.get("route_destination"),
                    "status": candidate.get("status"),
                    "resolution_minutes": _resolution_minutes(candidate),
                    "similarity_score": (
                        (0.55 if category_match else 0)
                        + (0.25 if priority_match else 0)
                    ),
                }
            )
        repeated_category = category_count >= 3
        similar_incidents.sort(
            key=lambda item: (
                -item["similarity_score"],
                -(
                    parse_utc(item["date"])
                    or datetime(1970, 1, 1, tzinfo=timezone.utc)
                ).timestamp(),
            )
        )
        similar_incidents = similar_incidents[:10]
        response_history = [
            {
                "date": item["date"],
                "category": item["category"],
                "priority": item["priority"],
                "distance_km": None,
                "department": item["department"],
                "destination": item["destination"],
                "status": item["status"],
                "resolution_minutes": item["resolution_minutes"],
                "response_information": (
                    "Response information unavailable."
                    if not item["department"] and not item["destination"]
                    else None
                ),
            }
            for item in similar_incidents
        ]
        prevention = {
            "pattern_detected": repeated_category,
            "message": (
                (
                    f"{category_count} {report.get('emergency_type')} reports "
                    "appear in ResQNet records. This is a network-level pattern; "
                    "no spatial relationship is inferred."
                )
                if repeated_category
                else (
                    "Location unavailable. General category guidance is based on "
                    "the incident type; no spatial relationship is inferred."
                )
            ),
            "suggestions": list(
                PREVENTION_SUGGESTIONS.get(report.get("emergency_type"), ())
            ),
        }
        network_analytics = build_global_intelligence(reports, now=now)
        return {
            "radius_km": radius_km,
            "analysis_scope": (
                "Location unavailable. Nearby incidents, hotspots and area risk "
                "require a valid incident location. Similar cases use category and "
                "priority only."
            ),
            "gps_available": False,
            "general_intelligence": _general_intelligence(
                reports, similar_incidents, response_history, prevention, now
            ),
            "location_intelligence": {
                "available": False,
                "status": "unavailable",
                "message": (
                    "Location unavailable. Nearby incidents, hotspots and area risk "
                    "require a valid incident location."
                ),
            },
            "short_term_concentration": {
                "available": False,
                "detected": False,
                "message": "Unavailable because this report has no valid GPS location.",
                "window_hours": SHORT_TERM_WINDOW_HOURS,
            },
            "extreme_proximity": {
                "available": False,
                "detected": False,
                "message": "Unavailable because this report has no valid GPS location.",
                "threshold_km": EXTREME_PROXIMITY_KM,
                "count": None,
                "incidents": [],
            },
            "recurring_pattern": {
                "available": False,
                "detected": False,
                "message": "Unavailable because this report has no valid GPS location.",
                "minimum_incidents": MIN_RECURRING_INCIDENTS,
                "minimum_distinct_dates": MIN_RECURRING_DISTINCT_DATES,
            },
            "evidence_strength": "unavailable",
            "evidence_explanation": (
                "Location-specific evidence is unavailable because this report has "
                "no valid GPS location."
            ),
            "observed_local_problem": "unavailable",
            "local_problem": "unavailable",
            "local_problem_reason": (
                "A local problem cannot be assessed without a valid incident location."
            ),
            "recommendation": "unavailable",
            "recommendation_reason": (
                "A location-specific recommendation cannot be assessed without a "
                "valid incident location."
            ),
            "recommendation_basis": {
                "available": False,
                "message": "No location-based evidence was evaluated.",
            },
            "location_conclusion": "unavailable",
            "conclusion_reason": (
                "A location conclusion cannot be assessed without a valid incident location."
            ),
            "data_limitation": (
                "This report has no valid GPS location; no location-specific pattern, "
                "cause, or recommendation can be established."
            ),
            "previous_nearby_count": 0,
            "nearby_cases": [],
            "similar_incidents": similar_incidents,
            "area_analytics": {
                "total_incidents": 0,
                "most_common_category": None,
                "category_distribution": _counter_data([], "emergency_type", CATEGORY_LABELS),
                "priority_distribution": _counter_data([], "priority", PRIORITY_LABELS),
                "status_distribution": _counter_data([], "status", STATUS_LABELS),
                "high_priority_cases": 0,
                "repeat_cases": 0,
                "repeat_pattern_detected": False,
                "resolution_rate_percentage": 0,
                "average_resolution_minutes": None,
                "average_resolution_unavailable": True,
                "most_active_time_period": None,
                "time_period_pattern": [],
                "recent_activity_30_days": 0,
                "monthly_trend": [],
            },
            "hotspots": {
                "count": 0,
                "clusters": [],
                "insufficient_data": True,
                "message": (
                    "Location unavailable. Nearby incidents, hotspots and area risk "
                    "require a valid incident location."
                ),
            },
            "risk_indicator": {
                "available": False,
                "score": None,
                "level": None,
                "message": (
                    "Location unavailable. Nearby incidents, hotspots and area risk "
                    "require a valid incident location."
                ),
                "calculation": {
                    "frequency_weight": 25,
                    "repeat_weight": 30,
                    "high_priority_weight": 20,
                    "recent_activity_weight": 15,
                    "hotspot_density_weight": 10,
                },
            },
            "response_history": response_history,
            "prevention": prevention,
            "official_historical_data": official_data,
            "combined_evidence": _make_combined_evidence(0, None),
            "future_risk_model": {
                "available": False,
                "message": "Future risk model requires additional historical records.",
            },
            "network_analytics": network_analytics,
        }
    report_time = parse_utc(report.get("created_at"))
    earlier_reports = []
    for candidate in reports:
        if candidate.get("id") == report.get("id"):
            continue
        if not isinstance(candidate.get("latitude"), (int, float)) or not isinstance(
            candidate.get("longitude"), (int, float)
        ):
            continue
        distance = haversine_km(
            report["latitude"],
            report["longitude"],
            candidate["latitude"],
            candidate["longitude"],
        )
        candidate_time = parse_utc(candidate.get("created_at"))
        if distance <= radius_km and (
            report_time is None or candidate_time is None or candidate_time <= report_time
        ):
            item = dict(candidate)
            item["distance_km"] = round(distance, 2)
            item["_distance_km"] = distance
            earlier_reports.append(item)

    area_reports = [dict(report), *earlier_reports]
    short_term = _detect_short_term_concentration(area_reports, report.get("id"))
    location_assessment = _location_assessment(
        report,
        earlier_reports,
        area_reports,
        radius_km,
        short_term,
    )
    same_category = [
        item for item in earlier_reports
        if item.get("emergency_type") == report.get("emergency_type")
    ]
    same_category_count = len(same_category) + 1
    category_counts = Counter(item.get("emergency_type") for item in area_reports)
    high_priority_count = sum(item.get("priority") == "High" for item in area_reports)
    resolved_count = sum(item.get("status") == "Resolved" for item in area_reports)
    durations = [
        duration for item in area_reports
        if (duration := _resolution_minutes(item)) is not None
    ]
    period_counts = Counter()
    recent_cutoff = now - timedelta(days=30)
    recent_count = 0
    for item in area_reports:
        created = parse_utc(item.get("created_at"))
        if not created:
            continue
        hour = created.astimezone(IST).hour
        period = (
            "Overnight" if hour < 6 else
            "Morning" if hour < 12 else
            "Afternoon" if hour < 17 else
            "Evening" if hour < 21 else
            "Overnight"
        )
        period_counts[period] += 1
        recent_count += created >= recent_cutoff

    area_hotspots = _cluster_gps_reports(area_reports, radius_km=radius_km)
    repeat_detected = same_category_count >= 3
    total_area = len(area_reports)
    insufficient = total_area < 2
    risk_score = None
    risk_level = None
    if not insufficient:
        frequency_score = min(total_area / 20, 1) * 25
        repeat_score = min(max(same_category_count - 1, 0) / 8, 1) * 30
        high_priority_score = (high_priority_count / total_area) * 20
        recent_score = (recent_count / total_area) * 15
        hotspot_score = min(sum(item["incident_count"] for item in area_hotspots) / total_area, 1) * 10
        risk_score = round(frequency_score + repeat_score + high_priority_score + recent_score + hotspot_score)
        risk_level = "HIGH" if risk_score >= 67 else "MEDIUM" if risk_score >= 34 else "LOW"

    recent_incidents = sorted(
        earlier_reports,
        key=lambda item: parse_utc(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:10]
    similar = []
    for item in earlier_reports:
        category_match = item.get("emergency_type") == report.get("emergency_type")
        priority_match = item.get("priority") == report.get("priority")
        if not category_match and not priority_match:
            continue
        time_days = abs(
            ((parse_utc(item.get("created_at")) or now) - (report_time or now)).total_seconds()
        ) / 86400
        similarity = (
            (0.55 if category_match else 0)
            + (0.25 if priority_match else 0)
            + 0.20 * max(0, 1 - item["distance_km"] / radius_km)
        )
        if time_days > 365:
            similarity *= 0.8
        item["similarity_score"] = round(similarity, 3)
        similar.append(item)
    similar.sort(key=lambda item: (-item["similarity_score"], item["distance_km"]))
    similar = similar[:10]

    average_resolution = _average(durations)
    most_common_category = category_counts.most_common(1)[0][0] if category_counts else None
    active_hours = period_counts.most_common(1)[0][0] if period_counts else None
    suggestions = (
        PREVENTION_SUGGESTIONS.get(report.get("emergency_type"), ())
        if repeat_detected else ()
    )
    response_history = [
        {
            "date": item.get("created_at"),
            "category": item.get("emergency_type"),
            "priority": item.get("priority"),
            "distance_km": item["distance_km"],
            "department": item.get("route_department"),
            "destination": item.get("route_destination"),
            "status": item.get("status"),
            "resolution_minutes": _resolution_minutes(item),
            "response_information": (
                "Response information unavailable."
                if not item.get("route_department") and not item.get("route_destination")
                else None
            ),
        }
        for item in recent_incidents
    ]
    prevention = {
        "pattern_detected": repeat_detected,
        "message": "Suggested preventive considerations based on historical incident patterns.",
        "suggestions": list(suggestions),
    }
    prevention["pattern_detected"] = (
        repeat_detected
        or short_term["detected"]
        or location_assessment["recurring_pattern"]["detected"]
    )
    prevention["message"] = location_assessment["recommendation_reason"]
    prevention["suggestions"] = list(
        dict.fromkeys(
            [location_assessment["recommendation"], *prevention["suggestions"]]
        )
    )
    similar_incidents = [
        {
            "id": item.get("id"),
            "date": item.get("created_at"),
            "category": item.get("emergency_type"),
            "priority": item.get("priority"),
            "distance_km": item["distance_km"],
            "department": item.get("route_department"),
            "destination": item.get("route_destination"),
            "status": item.get("status"),
            "resolution_minutes": _resolution_minutes(item),
            "similarity_score": item["similarity_score"],
        }
        for item in similar
    ]
    return {
        "radius_km": radius_km,
        "analysis_scope": "GPS-based analysis of prior reports within the selected radius.",
        "gps_available": True,
        "general_intelligence": _general_intelligence(
            reports, similar_incidents, response_history, prevention, now
        ),
        "location_intelligence": {
            "available": True,
            "status": "available",
            "message": None,
        },
        **location_assessment,
        "previous_nearby_count": len(earlier_reports),
        "nearby_cases": [
            {
                "id": item.get("id"),
                "date": item.get("created_at"),
                "category": item.get("emergency_type"),
                "priority": item.get("priority"),
                "distance_km": item["distance_km"],
                "department": item.get("route_department"),
                "destination": item.get("route_destination"),
                "status": item.get("status"),
                "resolution_minutes": _resolution_minutes(item),
            }
            for item in recent_incidents
        ],
        "similar_incidents": similar_incidents,
        "area_analytics": {
            "total_incidents": total_area,
            "most_common_category": most_common_category,
            "category_distribution": _counter_data(area_reports, "emergency_type", CATEGORY_LABELS),
            "priority_distribution": _counter_data(area_reports, "priority", PRIORITY_LABELS),
            "status_distribution": _counter_data(area_reports, "status", STATUS_LABELS),
            "high_priority_cases": high_priority_count,
            "repeat_cases": same_category_count if repeat_detected else 0,
            "repeat_pattern_detected": repeat_detected,
            "resolution_rate_percentage": round(resolved_count * 100 / total_area, 1) if total_area else 0,
            "average_resolution_minutes": average_resolution,
            "average_resolution_unavailable": average_resolution is None,
            "most_active_time_period": active_hours,
            "time_period_pattern": [
                {"period": period, "count": period_counts[period]}
                for period in ("Morning", "Afternoon", "Evening", "Overnight")
            ],
            "recent_activity_30_days": recent_count,
            "monthly_trend": _monthly_trend(area_reports, now),
        },
        "hotspots": {
            "count": len(area_hotspots),
            "clusters": area_hotspots,
            "insufficient_data": not bool(area_hotspots),
            "message": "Insufficient data for hotspot detection." if not area_hotspots else None,
        },
        "risk_indicator": {
            "available": not insufficient,
            "score": risk_score,
            "level": risk_level,
            "message": (
                "Prototype historical risk indicator — not an official safety rating."
                if not insufficient else "Insufficient historical data."
            ),
            "calculation": {
                "frequency_weight": 25,
                "repeat_weight": 30,
                "high_priority_weight": 20,
                "recent_activity_weight": 15,
                "hotspot_density_weight": 10,
            },
        },
        "response_history": response_history,
        "prevention": prevention,
        "official_historical_data": official_data,
        "combined_evidence": _make_combined_evidence(len(earlier_reports), radius_km),
        "future_risk_model": {
            "available": False,
            "message": "Future risk model requires additional historical records.",
        },
    }
