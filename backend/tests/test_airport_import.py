import csv
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from scripts.import_airports import COLUMNS, clean_airports, import_records


class AirportImportTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        root = Path(self.tempdir.name)
        self.csv_path = root / "sample.csv"
        self.db_path = root / "app.db"

    def write_csv(self, rows):
        with self.csv_path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def row(**changes):
        data = dict(id="1", ident="KCLL", type="medium_airport",
                    name="Easterwood Field", municipality="College Station",
                    iso_country="US", iso_region="US-TX", iata_code="CLL",
                    icao_code="KCLL", latitude_deg="30.5886",
                    longitude_deg="-96.3638", scheduled_service="yes")
        data.update(changes)
        return data

    def test_filters_missing_iata_and_invalid_coordinates(self):
        self.write_csv([
            self.row(),
            self.row(id="2", iata_code="", ident="XX"),
            self.row(id="3", iata_code="BAD", latitude_deg="93"),
            self.row(id="4", iata_code="SEA", municipality="", icao_code=""),
        ])
        records, stats = clean_airports(self.csv_path)
        self.assertEqual(len(records), 2)
        self.assertEqual(stats["no_iata_code"], 1)
        self.assertEqual(stats["invalid_id_or_coordinates"], 1)
        sea = next(row for row in records if row[7] == "SEA")
        self.assertIsNone(sea[4])
        self.assertIsNone(sea[8])

    def test_refresh_preserves_other_tables_and_is_idempotent(self):
        self.write_csv([self.row(), self.row(id="2", ident="KDFW", name="DFW Airport",
                                             iata_code="DFW")])
        records, _ = clean_airports(self.csv_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO users VALUES (1, 'Existing User')")
            conn.commit()
        self.assertEqual(import_records(records, self.db_path), 2)
        self.assertEqual(import_records(records, self.db_path), 2)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT name FROM users WHERE id=1").fetchone()[0],
                             "Existing User")
            self.assertEqual(conn.execute("SELECT name FROM airports WHERE iata_code='CLL'").fetchone()[0],
                             "Easterwood Field")
            indexes = {i[1] for i in conn.execute("PRAGMA index_list(airports)")}
            self.assertIn("ix_airports_iata_code", indexes)

    def test_duplicate_iata_prefers_scheduled_and_larger_airport(self):
        self.write_csv([
            self.row(),
            self.row(id="2", ident="XX", iata_code="CLL", type="large_airport",
                     name="Other Airport", scheduled_service="no"),
            self.row(id="3", ident="ZZ", iata_code="CLL", type="large_airport",
                     name="Best Airport", scheduled_service="yes"),
        ])
        records, stats = clean_airports(self.csv_path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][3], "Best Airport")
        self.assertEqual(stats["duplicate_iata"], 2)

    def test_no_valid_data_does_not_change_existing_airports(self):
        self.write_csv([self.row()])
        records, _ = clean_airports(self.csv_path)
        import_records(records, self.db_path)
        self.write_csv([self.row(iata_code="")])
        with self.assertRaisesRegex(ValueError, "No valid"):
            clean_airports(self.csv_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
