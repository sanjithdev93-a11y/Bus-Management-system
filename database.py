"""Database helper module: connection, schema, sample data and query helpers."""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "college_bus.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    admin_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routes (
    route_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    route_name  TEXT NOT NULL UNIQUE,
    start_point TEXT NOT NULL,
    destination TEXT NOT NULL,
    stops       TEXT
);

CREATE TABLE IF NOT EXISTS buses (
    bus_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_number          TEXT NOT NULL UNIQUE,
    registration_number TEXT NOT NULL UNIQUE,
    capacity            INTEGER NOT NULL CHECK (capacity > 0),
    route_id            INTEGER REFERENCES routes(route_id) ON DELETE RESTRICT,
    driver_id           INTEGER UNIQUE REFERENCES drivers(driver_id) ON DELETE SET NULL,
    status              TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive'))
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    phone          TEXT NOT NULL,
    licence_number TEXT NOT NULL UNIQUE,
    bus_id         INTEGER UNIQUE REFERENCES buses(bus_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    department TEXT NOT NULL,
    year       INTEGER NOT NULL CHECK (year BETWEEN 1 AND 4),
    phone      TEXT NOT NULL,
    bus_id     INTEGER REFERENCES buses(bus_id) ON DELETE RESTRICT
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite needs this on every connection
    return conn


def query(sql, params=(), one=False):
    """Run a SELECT with parameters. Returns a list of rows (or one row / None)."""
    conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def transaction(work):
    """Run work(conn) in one transaction: commit on success, roll back on any error."""
    conn = get_conn()
    try:
        with conn:
            return work(conn)
    finally:
        conn.close()


def init_db():
    """Create tables and, on first run only, insert clearly marked sample records."""
    def work(c):
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM routes").fetchone()[0] > 0:
            return
        c.execute("INSERT INTO routes (route_name, start_point, destination, stops) VALUES (?,?,?,?)",
                  ("[Sample] Route A", "Central Bus Stand", "College Campus", "Market Road, Railway Station, Hospital Junction"))
        c.execute("INSERT INTO routes (route_name, start_point, destination, stops) VALUES (?,?,?,?)",
                  ("[Sample] Route B", "North Town", "College Campus", "Temple Street, Park Gate"))
        c.execute("INSERT INTO buses (bus_number, registration_number, capacity, route_id, status) VALUES (?,?,?,?,?)",
                  ("BUS-01", "SAMPLE-0001", 40, 1, "Active"))
        c.execute("INSERT INTO buses (bus_number, registration_number, capacity, route_id, status) VALUES (?,?,?,?,?)",
                  ("BUS-02", "SAMPLE-0002", 35, 2, "Inactive"))
        c.execute("INSERT INTO drivers (name, phone, licence_number, bus_id) VALUES (?,?,?,?)",
                  ("Sample Driver One", "9000000001", "SAMPLE-DL-001", 1))
        c.execute("UPDATE buses SET driver_id = 1 WHERE bus_id = 1")
        c.execute("INSERT INTO drivers (name, phone, licence_number) VALUES (?,?,?)",
                  ("Sample Driver Two", "9000000002", "SAMPLE-DL-002"))
        c.execute("INSERT INTO students VALUES (?,?,?,?,?,?)",
                  ("SAMPLE001", "Sample Student One", "Computer Science", 2, "9000000011", 1))
        c.execute("INSERT INTO students VALUES (?,?,?,?,?,?)",
                  ("SAMPLE002", "Sample Student Two", "Mechanical", 3, "9000000012", 2))
    transaction(work)
