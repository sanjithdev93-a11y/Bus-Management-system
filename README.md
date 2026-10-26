# College Bus Management System
Flask + SQLite mini project for Database Systems (CRUD, constraints, JOINs).

## 1. Setup on Ubuntu (step by step)
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip   # 1. Python tools
cd college-bus-management                                                 # 2. enter project folder
python3 -m venv venv                                                      # 3. create virtual environment
source venv/bin/activate                                                  # 4. activate it (prompt shows "(venv)")
pip install -r requirements.txt                                           # 5. install Flask
python create_admin.py                                                    # 6. create admin (you choose username/password)
python app.py                                                             # 7. start server
```
Open **http://127.0.0.1:5000** in the browser. Stop the server with `Ctrl+C`.
Next time: `source venv/bin/activate && python app.py`.

`college_bus.db` is created automatically on first start with a few records marked "Sample".

## 2. Admin credentials
No password is stored in code. `create_admin.py` asks for a username and password and stores only a
**hashed** password (Werkzeug) in the `admins` table. Run it again to reset the password.
Login is checked on the backend and kept in a Flask session; every admin route uses `@login_required`.
Optional: `export SECRET_KEY="long-random-text"` before starting (otherwise a random key is saved in `secret.key`).
The read-only page `/info` (linked from the login page) needs no login and shows no phone/licence data.

## 3. Database schema
| Table | Primary key | Foreign keys | Other constraints |
|---|---|---|---|
| admins | admin_id | – | username UNIQUE |
| routes | route_id | – | route_name UNIQUE |
| buses | bus_id | route_id → routes (ON DELETE RESTRICT); driver_id → drivers (ON DELETE SET NULL) | bus_number UNIQUE, registration_number UNIQUE, capacity > 0, status IN ('Active','Inactive') |
| drivers | driver_id | bus_id → buses (ON DELETE SET NULL) | licence_number UNIQUE |
| students | student_id (text, e.g. roll no.) | bus_id → buses (ON DELETE RESTRICT) | year BETWEEN 1 AND 4 |

Relationships: one route has many buses; one bus has many students; one bus has at most one driver (1:1).
`PRAGMA foreign_keys = ON` is set on every connection, so invalid references are rejected by SQLite itself.
* A route used by buses cannot be deleted; a bus that still has students cannot be deleted (RESTRICT).
* Deleting a driver or a bus just clears the link on the other side (SET NULL).
* Because the spec stores the bus–driver link in both `buses.driver_id` and `drivers.bus_id`, the app keeps
  them in sync in one transaction (`set_link()` in app.py). Mention this in the viva if asked about redundancy.

## 4. SQL used (all parameterized with `?`)
```sql
-- INSERT
INSERT INTO routes (route_name, start_point, destination, stops) VALUES (?,?,?,?);
-- UPDATE
UPDATE buses SET bus_number=?, registration_number=?, capacity=?, route_id=?, status=? WHERE bus_id=?;
-- DELETE
DELETE FROM students WHERE student_id = ?;
-- WHERE (search)
SELECT ... FROM buses b ... WHERE b.bus_number LIKE ?;
-- JOIN: bus number + route name + driver name
SELECT b.bus_number, r.route_name, d.name AS driver_name
FROM buses b
LEFT JOIN routes  r ON b.route_id  = r.route_id
LEFT JOIN drivers d ON b.driver_id = d.driver_id;
-- JOIN across three tables: student -> bus -> route
SELECT s.name, b.bus_number, r.route_name
FROM students s
LEFT JOIN buses  b ON s.bus_id  = b.bus_id
LEFT JOIN routes r ON b.route_id = r.route_id;
-- JOIN + GROUP BY: buses per route
SELECT r.route_name, COUNT(b.bus_id) FROM routes r LEFT JOIN buses b ON b.route_id = r.route_id GROUP BY r.route_id;
```
LEFT JOIN is used so buses without a route/driver still appear.

## 5. Demo scenarios for evaluation
1. **Login security:** open `/buses` without logging in → redirected to login. Wrong password → error message.
2. **INSERT:** Routes → add "Route C" with stops. Dashboard route count increases.
3. **INSERT + JOIN:** Buses → add BUS-03 with Route C and a driver. The table shows route name and driver name together.
4. **UPDATE:** Click Edit on BUS-03, change capacity/status to Inactive, save. Dashboard badge changes.
5. **WHERE / search:** type `BUS-0` in the bus search box → filtered rows.
6. **Duplicate constraint:** add another bus with number BUS-03 → "Duplicate value" error, nothing inserted.
7. **Foreign key protection:** try deleting "[Sample] Route A" (used by BUS-01) → blocked with message.
   Delete a bus that has students → blocked. Delete a student first, then the bus works.
8. **Capacity check:** set a bus capacity to 1, assign two students → second one rejected ("bus is full").
9. **DELETE:** delete a student/driver → record disappears and counts update.
10. **Show the data is real:** `sqlite3 college_bus.db "SELECT * FROM buses;"` (install with `sudo apt install sqlite3`).
11. **SQL injection attempt:** search for `' OR 1=1 --` → treated as plain text, no results.

## 6. Project files
`app.py` routes/validation/CSRF · `database.py` connection, schema, sample data · `create_admin.py` admin setup ·
`templates/` pages · `static/` CSS and JS (JS only asks for delete confirmation; all data work is SQL in Python).
