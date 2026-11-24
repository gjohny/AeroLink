"""Clean OurAirports CSV and import into existing SQLite database.

Run from backend/:  python -m scripts.import_airports [path/to/airports.csv]
"""

import argparse
import csv
import math
import re
import sqlite3
from contextlib import closing
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = BACKEND_DIR / "data" / "airports_cleaned.csv"
DEFAULT_DATABASE = BACKEND_DIR / "instance" / "app.db"

COLUMNS = (
    "id", "ident", "type", "name", "municipality", "iso_country",
    "iso_region", "iata_code", "icao_code", "latitude_deg",
    "longitude_deg", "scheduled_service",
)
REQUIRED_INPUT = set(COLUMNS)
IATA_RE = re.compile(r"[A-Z]{3}")
COUNTRY_RE = re.compile(r"[A-Z]{2}")
ICAO_RE = re.compile(r"[A-Z0-9]{4}")
ALLOWED_TYPES = {
    "large_airport", "medium_airport", "small_airport",
    "seaplane_base", "heliport",
}
TYPE_RANK = {
    "large_airport": 5, "medium_airport": 4, "small_airport": 3,
    "seaplane_base": 2, "heliport": 1,
}


# Matching columns and indexes are defined in backend/app/models.py.
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS airports (
    id INTEGER NOT NULL PRIMARY KEY,
    ident VARCHAR(12) NOT NULL,
    type VARCHAR(32) NOT NULL,
    name VARCHAR(255) NOT NULL,
    municipality VARCHAR(160),
    iso_country VARCHAR(2) NOT NULL,
    iso_region VARCHAR(16),
    iata_code VARCHAR(3) NOT NULL,
    icao_code VARCHAR(4),
    latitude_deg FLOAT NOT NULL,
    longitude_deg FLOAT NOT NULL,
    scheduled_service BOOLEAN NOT NULL
)
"""
INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_airports_iata_code ON airports (iata_code)",
    "CREATE INDEX IF NOT EXISTS ix_airports_icao_code ON airports (icao_code)",
    "CREATE INDEX IF NOT EXISTS ix_airports_iso_country ON airports (iso_country)",
    "CREATE INDEX IF NOT EXISTS ix_airports_country_municipality "
    "ON airports (iso_country, municipality)",
)
INSERT_SQL = (
    "INSERT INTO airports (" + ", ".join(COLUMNS) + ") VALUES ("
    + ", ".join("?" for _ in COLUMNS) + ")"
)


def _optional(value):
    return value.strip() or None


def _clean_row(row):
    """Return a normalized record or (None, reason_for_skipping)."""
    iata = row["iata_code"].strip().upper()
    if not iata:
        return None, "no_iata_code"
    if not IATA_RE.fullmatch(iata):
        return None, "bad_iata_code"

    airport_type = row["type"].strip().lower()
    if airport_type not in ALLOWED_TYPES:
        return None, "not_active_airport_type"

    try:
        airport_id = int(row["id"].strip())
        lat = float(row["latitude_deg"].strip())
        lon = float(row["longitude_deg"].strip())
    except (ValueError, TypeError):
        return None, "invalid_id_or_coordinates"
    if airport_id <= 0 or not (math.isfinite(lat) and math.isfinite(lon)):
        return None, "invalid_id_or_coordinates"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, "invalid_id_or_coordinates"

    name = row["name"].strip()
    ident = row["ident"].strip().upper()
    country = row["iso_country"].strip().upper()
    if not name or not ident or not COUNTRY_RE.fullmatch(country):
        return None, "missing_identity_or_country"
    if len(name) > 255 or len(ident) > 12:
        return None, "overlong_identity"

    icao = (row.get("icao_code") or "").strip().upper()
    if icao and not ICAO_RE.fullmatch(icao):
        icao = ""  # Bad optional code need not invalidate an otherwise useful airport.

    service = row["scheduled_service"].strip().lower()
    if service not in ("yes", "no", "1", "0", "true", "false"):
        return None, "invalid_scheduled_service"
    scheduled = 1 if service in ("yes", "1", "true") else 0
    municipality = _optional(row["municipality"])
    region = _optional(row["iso_region"])
    if municipality and len(municipality) > 160:
        return None, "overlong_municipality"
    if region and len(region) > 16:
        return None, "overlong_region"

    return (
        airport_id, ident, airport_type, name, municipality, country,
        region, iata, icao or None, lat, lon, scheduled,
    ), None


def clean_airports(csv_path):
    """Load source data, keep valid IATA-coded locations, and return counts.

    In the rare case of repeated IATA codes, prefer scheduled-service airports
    and then larger airports. The provided OurAirports file has no duplicates.
    """
    chosen_by_iata = {}
    stats = Counter()
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV is empty or has no header")
        missing = REQUIRED_INPUT - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing required CSV columns: {', '.join(sorted(missing))}")

        for row in reader:
            stats["source_rows"] += 1
            if None in row or any(row.get(column) is None for column in REQUIRED_INPUT):
                stats["malformed_csv_row"] += 1
                continue
            record, reason = _clean_row(row)
            if reason:
                stats[reason] += 1
                continue
            code = record[COLUMNS.index("iata_code")]
            if code in chosen_by_iata:
                stats["duplicate_iata"] += 1
                old = chosen_by_iata[code]
                old_score = (old[-1], TYPE_RANK[old[2]])
                new_score = (record[-1], TYPE_RANK[record[2]])
                if new_score > old_score:
                    chosen_by_iata[code] = record
            else:
                chosen_by_iata[code] = record

    # Sort records so the cleaned CSV and import are deterministic.
    cleaned = [chosen_by_iata[code] for code in sorted(chosen_by_iata)]
    ids = {row[0] for row in cleaned}
    if len(ids) != len(cleaned):
        raise ValueError("Multiple airport codes map to the same source ID")
    if not cleaned:
        raise ValueError("No valid IATA-coded airports found; the existing database is unchanged")
    stats["imported_rows"] = len(cleaned)
    return cleaned, stats


def save_cleaned_csv(records, csv_path):
    """Optional: save the reduced dataset with just the 12 needed columns."""
    out = Path(csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for record in records:
            writer.writerow(record)


def import_records(records, db_path):
    """Refresh only the airports table, preserving other AeroLink tables.

    The DELETE and bulk insert run in a single transaction. An exception rolls
    them back, so an unsuccessful refresh does not partially replace airport data.
    """
    if not records:
        raise ValueError("Refusing to import an empty airport dataset")
    dest = Path(db_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(dest, timeout=30)) as conn:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute(TABLE_SQL)
        for index in INDEXES:
            conn.execute(index)
        with conn:
            conn.execute("DELETE FROM airports")
            conn.executemany(INSERT_SQL, records)
        count = conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
        if count != len(records):
            raise RuntimeError(f"Airport import count mismatch: expected {len(records)}, got {count}")
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE,
                        help="OurAirports raw CSV or the included reduced CSV")
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE,
                        help="SQLite file; defaults to backend/instance/app.db")
    parser.add_argument("--cleaned-output", type=Path,
                        help="Also save normalized airport rows to this CSV")
    args = parser.parse_args(argv)

    records, counts = clean_airports(args.source)
    if args.cleaned_output:
        save_cleaned_csv(records, args.cleaned_output)
    imported = import_records(records, args.db)
    print(f"Source rows: {counts['source_rows']:,}")
    print(f"Imported airports: {imported:,}")
    for key in sorted(counts):
        if key not in ("source_rows", "imported_rows") and counts[key]:
            print(f"Skipped {key}: {counts[key]:,}")
    print(f"SQLite database: {args.db.resolve()}")
    if args.cleaned_output:
        print(f"Cleaned CSV: {args.cleaned_output.resolve()}")


if __name__ == "__main__":
    main()
