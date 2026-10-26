"""College Bus Management System - Flask application."""
import os
import re
import secrets
import sqlite3
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import database as db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


def load_secret_key():
    """Use SECRET_KEY from the environment, else generate one once and keep it in secret.key."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(BASE_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app.secret_key = load_secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
db.init_db()

# ---------------------------------------------------------------- security
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def verify_csrf():
    if request.method == "POST":
        sent, real = request.form.get("_csrf", ""), session.get("_csrf", "")
        if not real or not secrets.compare_digest(sent, real):
            abort(400, "Invalid or missing CSRF token. Go back, refresh the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            flash("Please log in as administrator.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- helpers
def field(name):
    return request.form.get(name, "").strip()


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def valid_phone(p):
    return bool(re.fullmatch(r"[0-9+\- ]{7,15}", p))


def explain(err):
    msg = str(err)
    if msg.startswith("UNIQUE"):
        col = msg.split(".")[-1].replace("_", " ")
        return f"Duplicate value: that {col} already exists."
    if "FOREIGN KEY" in msg:
        return ("Operation blocked: this record is still linked to other records "
                "(e.g. a route used by buses, or a bus that has students), or it refers to a record that does not exist.")
    return "Invalid data: a database constraint was violated."


def perform(work, ok_message, endpoint):
    """Run a database change in a transaction and flash a friendly result."""
    try:
        db.transaction(work)
        flash(ok_message, "success")
    except ValueError as e:                 # our own validation messages
        flash(str(e), "error")
    except LookupError:
        flash("Record not found (it may have been deleted).", "error")
    except sqlite3.IntegrityError as e:
        flash(explain(e), "error")
    except sqlite3.Error:
        flash("A database error occurred. Please try again.", "error")
    return redirect(url_for(endpoint))


def get_edit(table, pk):
    """Load the record named in ?edit=... so the form can be pre-filled."""
    key = request.args.get("edit")
    if not key:
        return None
    row = db.query(f"SELECT * FROM {table} WHERE {pk} = ?", (key,), one=True)  # table/pk are fixed constants
    if row is None:
        flash("Record to edit was not found.", "error")
    return row


def set_link(c, bus_id, driver_id):
    """Keep buses.driver_id and drivers.bus_id consistent (one driver <-> one bus)."""
    c.execute("UPDATE buses   SET driver_id = NULL WHERE bus_id = ? OR driver_id = ?", (bus_id, driver_id))
    c.execute("UPDATE drivers SET bus_id    = NULL WHERE bus_id = ? OR driver_id = ?", (bus_id, driver_id))
    if bus_id is not None and driver_id is not None:
        c.execute("UPDATE buses   SET driver_id = ? WHERE bus_id = ?", (driver_id, bus_id))
        c.execute("UPDATE drivers SET bus_id    = ? WHERE driver_id = ?", (bus_id, driver_id))


BUS_SQL = """
SELECT b.bus_id, b.bus_number, b.registration_number, b.capacity, b.status,
       r.route_name, d.name AS driver_name
FROM buses b
LEFT JOIN routes  r ON b.route_id  = r.route_id
LEFT JOIN drivers d ON b.driver_id = d.driver_id
"""

# ---------------------------------------------------------------- auth
@app.route("/")
def index():
    return redirect(url_for("dashboard" if session.get("admin") else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        row = db.query("SELECT * FROM admins WHERE username = ?", (field("username"),), one=True)
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            session.clear()
            session["admin"] = row["username"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------- public read-only page
@app.route("/info")
def info():
    return render_template("info.html",
                           buses=db.query(BUS_SQL + " ORDER BY b.bus_number"),
                           route_list=db.query("SELECT * FROM routes ORDER BY route_name"))


# ---------------------------------------------------------------- dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    counts = db.query("""SELECT (SELECT COUNT(*) FROM buses)    AS buses,
                                (SELECT COUNT(*) FROM drivers)  AS drivers,
                                (SELECT COUNT(*) FROM students) AS students,
                                (SELECT COUNT(*) FROM routes)   AS routes""", one=True)
    return render_template("dashboard.html", counts=counts, buses=db.query(BUS_SQL + " ORDER BY b.bus_number"))


# ---------------------------------------------------------------- buses
@app.route("/buses")
@login_required
def buses():
    q = request.args.get("q", "").strip()
    if q:   # WHERE + LIKE search on bus number
        rows = db.query(BUS_SQL + " WHERE b.bus_number LIKE ? ORDER BY b.bus_number", (f"%{q}%",))
    else:
        rows = db.query(BUS_SQL + " ORDER BY b.bus_number")
    return render_template("buses.html", buses=rows, q=q, edit=get_edit("buses", "bus_id"),
                           route_opts=db.query("SELECT route_id, route_name FROM routes ORDER BY route_name"),
                           driver_opts=db.query("SELECT driver_id, name FROM drivers ORDER BY name"))


@app.post("/buses/save")
@login_required
def bus_save():
    bid, number, reg = to_int(field("bus_id")), field("bus_number"), field("registration_number")
    cap, route_id, driver_id, status = to_int(field("capacity")), to_int(field("route_id")), to_int(field("driver_id")), field("status")

    def work(c):
        if not number or not reg:
            raise ValueError("Bus number and registration number are required.")
        if cap is None or cap < 1 or cap > 100:
            raise ValueError("Capacity must be a number between 1 and 100.")
        if status not in ("Active", "Inactive"):
            raise ValueError("Status must be Active or Inactive.")
        if bid:
            cur = c.execute("UPDATE buses SET bus_number=?, registration_number=?, capacity=?, route_id=?, status=? WHERE bus_id=?",
                            (number, reg, cap, route_id, status, bid))
            if cur.rowcount == 0:
                raise LookupError
            new_id = bid
        else:
            new_id = c.execute("INSERT INTO buses (bus_number, registration_number, capacity, route_id, status) VALUES (?,?,?,?,?)",
                               (number, reg, cap, route_id, status)).lastrowid
        set_link(c, new_id, driver_id)

    return perform(work, "Bus saved successfully.", "buses")


# ---------------------------------------------------------------- drivers
@app.route("/drivers")
@login_required
def drivers():
    rows = db.query("""SELECT d.driver_id, d.name, d.phone, d.licence_number, d.bus_id, b.bus_number
                       FROM drivers d LEFT JOIN buses b ON d.bus_id = b.bus_id ORDER BY d.name""")
    return render_template("drivers.html", drivers=rows, edit=get_edit("drivers", "driver_id"),
                           bus_opts=db.query("SELECT bus_id, bus_number FROM buses ORDER BY bus_number"))


@app.post("/drivers/save")
@login_required
def driver_save():
    did, name, phone, lic, bus_id = to_int(field("driver_id")), field("name"), field("phone"), field("licence_number"), to_int(field("bus_id"))

    def work(c):
        if not name or not lic:
            raise ValueError("Name and licence number are required.")
        if not valid_phone(phone):
            raise ValueError("Enter a valid phone number (7-15 digits).")
        if did:
            cur = c.execute("UPDATE drivers SET name=?, phone=?, licence_number=? WHERE driver_id=?", (name, phone, lic, did))
            if cur.rowcount == 0:
                raise LookupError
            new_id = did
        else:
            new_id = c.execute("INSERT INTO drivers (name, phone, licence_number) VALUES (?,?,?)", (name, phone, lic)).lastrowid
        set_link(c, bus_id, new_id)

    return perform(work, "Driver saved successfully.", "drivers")


# ---------------------------------------------------------------- students
@app.route("/students")
@login_required
def students():
    rows = db.query("""SELECT s.student_id, s.name, s.department, s.year, s.phone, b.bus_number, r.route_name
                       FROM students s
                       LEFT JOIN buses  b ON s.bus_id  = b.bus_id
                       LEFT JOIN routes r ON b.route_id = r.route_id
                       ORDER BY s.student_id""")
    return render_template("students.html", students=rows, edit=get_edit("students", "student_id"),
                           bus_opts=db.query("SELECT bus_id, bus_number FROM buses ORDER BY bus_number"))


@app.post("/students/save")
@login_required
def student_save():
    orig, sid, name, dept = field("orig_id"), field("student_id"), field("name"), field("department")
    year, phone, bus_id = to_int(field("year")), field("phone"), to_int(field("bus_id"))

    def work(c):
        if not sid or not name or not dept:
            raise ValueError("Student ID, name and department are required.")
        if year not in (1, 2, 3, 4):
            raise ValueError("Year of study must be 1 to 4.")
        if not valid_phone(phone):
            raise ValueError("Enter a valid phone number (7-15 digits).")
        if bus_id is not None:
            bus = c.execute("SELECT capacity FROM buses WHERE bus_id=?", (bus_id,)).fetchone()
            if bus is None:
                raise ValueError("Selected bus does not exist.")
            used = c.execute("SELECT COUNT(*) FROM students WHERE bus_id=? AND student_id<>?", (bus_id, sid)).fetchone()[0]
            if used >= bus["capacity"]:
                raise ValueError("That bus is already full.")
        if orig:
            cur = c.execute("UPDATE students SET name=?, department=?, year=?, phone=?, bus_id=? WHERE student_id=?",
                            (name, dept, year, phone, bus_id, orig))
            if cur.rowcount == 0:
                raise LookupError
        else:
            c.execute("INSERT INTO students (student_id, name, department, year, phone, bus_id) VALUES (?,?,?,?,?,?)",
                      (sid, name, dept, year, phone, bus_id))

    return perform(work, "Student saved successfully.", "students")


# ---------------------------------------------------------------- routes
@app.route("/routes")
@login_required
def routes():
    rows = db.query("""SELECT r.*, COUNT(b.bus_id) AS bus_count
                       FROM routes r LEFT JOIN buses b ON b.route_id = r.route_id
                       GROUP BY r.route_id ORDER BY r.route_name""")
    return render_template("routes.html", route_rows=rows, edit=get_edit("routes", "route_id"))


@app.post("/routes/save")
@login_required
def route_save():
    rid, name, start, dest, stops = to_int(field("route_id")), field("route_name"), field("start_point"), field("destination"), field("stops")

    def work(c):
        if not name or not start or not dest:
            raise ValueError("Route name, starting point and destination are required.")
        if rid:
            cur = c.execute("UPDATE routes SET route_name=?, start_point=?, destination=?, stops=? WHERE route_id=?",
                            (name, start, dest, stops, rid))
            if cur.rowcount == 0:
                raise LookupError
        else:
            c.execute("INSERT INTO routes (route_name, start_point, destination, stops) VALUES (?,?,?,?)",
                      (name, start, dest, stops))

    return perform(work, "Route saved successfully.", "routes")


# ---------------------------------------------------------------- delete (POST only)
DELETABLE = {"buses": ("buses", "bus_id"), "drivers": ("drivers", "driver_id"),
             "students": ("students", "student_id"), "routes": ("routes", "route_id")}


@app.post("/<entity>/<key>/delete")
@login_required
def delete_record(entity, key):
    if entity not in DELETABLE:
        abort(404)
    table, pk = DELETABLE[entity]

    def work(c):
        if c.execute(f"DELETE FROM {table} WHERE {pk} = ?", (key,)).rowcount == 0:
            raise LookupError

    return perform(work, "Record deleted.", entity)


if __name__ == "__main__":
    app.run(debug=False)
