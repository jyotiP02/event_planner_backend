from flask import Flask, request, jsonify
from flask_cors import CORS
from models import db, bcrypt, User, Event, RSVP
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import json
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["http://localhost:3000"])

# 🔐 Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SECRET_KEY'] = 'super-secret-key'
app.config['JWT_SECRET_KEY'] = 'jwt-secret'

# 🔧 Init
db.init_app(app)
bcrypt.init_app(app)
jwt = JWTManager(app)

@app.route('/')
def home():
    return jsonify({"message": "Event Planner API is running!"})

# ✅ Signup
@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'User')

    if not name or not email or not password:
        return jsonify({'message': 'All fields are required'}), 400
    if len(password) < 6:
        return jsonify({'message': 'Password must be at least 6 characters'}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({'message': 'Email already registered'}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(name=name, email=email, password=hashed_password, role=role)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'Signup successful'}), 200

# 🔐 Login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data['email']
    password = data['password']

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({"message": "Invalid credentials"}), 401

    token = create_access_token(identity=json.dumps({"id": user.id, "role": user.role}))
    return jsonify({"token": token, "role": user.role, "name": user.name})

# 📅 Get Events
@app.route('/events', methods=['GET'])
@jwt_required()
def get_events():
    try:
        events = Event.query.order_by(Event.date.asc()).all()
        event_list = []
        for e in events:
            event_list.append({
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "date": str(e.date),
                "start_time": str(e.start_time),
                "end_time": str(e.end_time),
                "location": e.location,
                "image_url": e.image_url,
                "going": RSVP.query.filter_by(event_id=e.id, status="Going").count(),
                "maybe": RSVP.query.filter_by(event_id=e.id, status="Maybe").count(),
                "decline": RSVP.query.filter_by(event_id=e.id, status="Decline").count()
            })
        return jsonify({"events": event_list})
    except Exception as e:
        print("❌ Error in /events route:", str(e))
        return jsonify({"message": "Something went wrong", "error": str(e)}), 500

# ✅ RSVP to an event
@app.route('/rsvp/<int:event_id>', methods=['POST'])
@jwt_required()
def rsvp_event(event_id):
    identity = json.loads(get_jwt_identity())
    user_id = identity['id']

    data = request.json
    status = data.get("status")

    if not status:
        return jsonify({"message": "Status is required"}), 400

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"message": "Event not found"}), 404

    event_date = datetime.strptime(event.date, "%Y-%m-%d")
    if event_date < datetime.now():
        return jsonify({"message": "RSVP not allowed. Event date has passed."}), 400

    existing_rsvp = RSVP.query.filter_by(user_id=user_id, event_id=event_id).first()

    if existing_rsvp:
        existing_rsvp.status = status
    else:
        new_rsvp = RSVP(user_id=user_id, event_id=event_id, status=status)
        db.session.add(new_rsvp)

    db.session.commit()
    return jsonify({"message": f"RSVP updated to {status}"}), 200

# 🆕 Create Event
@app.route('/events', methods=['POST'])
@jwt_required()
def create_event():
    identity = json.loads(get_jwt_identity())
    if identity["role"] != "Admin":
        return jsonify({"message": "Unauthorized"}), 403

    data = request.json
    try:
        new_event = Event(
            title=data["title"],
            description=data["description"],
            date=data["date"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            location=data["location"],
            image_url=data.get("image_url")
        )
        db.session.add(new_event)
        db.session.commit()
        return jsonify({"message": "Event created!"}), 201
    except Exception as e:
        return jsonify({"message": "Failed to create event", "error": str(e)}), 500

# 🗑️ Delete Event
@app.route('/events/<int:event_id>', methods=['DELETE'])
@jwt_required()
def delete_event(event_id):
    identity = json.loads(get_jwt_identity())
    if identity["role"] != "Admin":
        return jsonify({"message": "Unauthorized"}), 403

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"message": "Event not found"}), 404

    db.session.delete(event)
    db.session.commit()
    return jsonify({"message": "Event deleted"}), 200

# ✏️ Update Event
@app.route('/events/<int:event_id>', methods=['PUT'])
@jwt_required()
def update_event(event_id):
    identity = json.loads(get_jwt_identity())
    if identity["role"] != "Admin":
        return jsonify({"message": "Unauthorized"}), 403

    data = request.json
    event = Event.query.get(event_id)
    if not event:
        return jsonify({"message": "Event not found"}), 404

    event.title = data.get("title", event.title)
    event.description = data.get("description", event.description)
    event.date = data.get("date", event.date)
    event.start_time = data.get("start_time", event.start_time)
    event.end_time = data.get("end_time", event.end_time)
    event.location = data.get("location", event.location)
    event.image_url = data.get("image_url", event.image_url)

    db.session.commit()
    return jsonify({"message": "Event updated"}), 200

# 📊 RSVP Summary
@app.route('/rsvp-summary/<int:event_id>', methods=['GET'])
@jwt_required()
def rsvp_summary(event_id):
    try:
        summary = {
            "Going": RSVP.query.filter_by(event_id=event_id, status="Going").count(),
            "Maybe": RSVP.query.filter_by(event_id=event_id, status="Maybe").count(),
            "Decline": RSVP.query.filter_by(event_id=event_id, status="Decline").count()
        }
        return jsonify(summary), 200
    except Exception as e:
        print("❌ Error in RSVP summary route:", str(e))
        return jsonify({"message": "Something went wrong", "error": str(e)}), 500

# 📄 View My RSVPs - ✅ Updated to match frontend structure
@app.route('/my-rsvps', methods=['GET'])
@jwt_required()
def my_rsvps():
    identity = json.loads(get_jwt_identity())
    user_id = identity['id']

    rsvps = RSVP.query.filter_by(user_id=user_id).all()
    data = []
    for rsvp in rsvps:
        event = Event.query.get(rsvp.event_id)
        if event:
            data.append({
                "status": rsvp.status,
                "event": {
                    "id": event.id,
                    "title": event.title,
                    "description": event.description,
                    "date": str(event.date),
                    "start_time": str(event.start_time),
                    "end_time": str(event.end_time),
                    "location": event.location,
                    "image": event.image,
                    "image_url": event.image_url
                }
            })

    return jsonify(rsvps=data), 200

# 🧪 Dummy event
@app.route('/create_dummy_event', methods=['GET'])
def create_dummy_event():
    new_event = Event(
        title="Diwali Celebration 🪔",
        description="Join us for lights, sweets, and joy!",
        date="2025-11-10",
        start_time="18:00",
        end_time="21:00",
        location="Community Hall, Delhi"
    )
    db.session.add(new_event)
    db.session.commit()
    return jsonify({"message": "Dummy event created!"}), 201

# ▶️ Run app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
