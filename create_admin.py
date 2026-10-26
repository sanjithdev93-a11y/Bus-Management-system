"""Create or reset the administrator account. Run:  python create_admin.py"""
import getpass
import sys
from werkzeug.security import generate_password_hash
import database as db

db.init_db()
username = input("Choose admin username: ").strip()
if not username:
    sys.exit("Username cannot be empty.")
password = getpass.getpass("Choose admin password (min 8 characters): ")
if len(password) < 8:
    sys.exit("Password too short.")
if password != getpass.getpass("Confirm password: "):
    sys.exit("Passwords do not match.")

hashed = generate_password_hash(password)
db.transaction(lambda c: c.execute(
    "INSERT INTO admins (username, password_hash) VALUES (?, ?) "
    "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash",
    (username, hashed)))
print(f"Admin '{username}' saved. You can now start the app with: python app.py")
