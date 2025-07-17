from models import db
from app import app

with app.app_context():
    db.drop_all()  # <-- optional, force refresh
    db.create_all()
    print("✅ Database initialized with tables.")
