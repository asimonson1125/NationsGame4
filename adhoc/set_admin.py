"""
Set a user to admin.
Usage: python3 adhoc/set_admin.py <username>
"""
import sys
from run import app
from app.models import User
from app import db

username = sys.argv[1] if len(sys.argv) > 1 else None
if not username:
    print("Usage: python3 adhoc/set_admin.py <username>")
    sys.exit(1)

with app.app_context():
    user = User.query.filter_by(username=username).first()
    if user:
        user.is_admin = True
        db.session.commit()
        print(f"User {user.username} is now an admin.")
    else:
        print("User not found.")
