"""
Examples:
  python -m scripts.check_airports --code CLL
  python -m scripts.check_airports --city Houston --country US
  python -m scripts.check_airports
"""

import argparse
import sqlite3
from pathlib import Path

from .import_airports import DEFAULT_DATABASE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--code", help="Exact IATA or ICAO airport code")
    parser.add_argument("--city", help="City/municipality name (partial match)")
    parser.add_argument("--country", help="Two-letter country code")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args(argv)
    if not args.db.is_file():
        parser.error(f"Database not found: {args.db}. Run python -m scripts.import_airports first")
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")

    with sqlite3.connect(args.db) as conn:
        total = conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
        print(f"Imported airports: {total:,}")
        where, params = [], []
        if args.code:
            where.append("(iata_code = ? OR icao_code = ?)")
            params += [args.code.strip().upper()] * 2
        if args.city:
            where.append("municipality LIKE ?")
            params.append("%" + args.city.strip() + "%")
        if args.country:
            where.append("iso_country = ?")
            params.append(args.country.strip().upper())
        sql = (
            "SELECT iata_code, icao_code, name, municipality, iso_country, "
            "latitude_deg, longitude_deg FROM airports"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY iata_code LIMIT ?"
        params.append(args.limit)
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("No matching airports.")
        return
    for iata, icao, name, city, country, lat, lon in rows:
        print(f"{iata} / {icao or '-'} | {name} | {city or 'Unknown city'}, {country} "
              f"| {lat:.5f}, {lon:.5f}")


if __name__ == "__main__":
    main()
