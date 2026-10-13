from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="SalesExecutive")
    active = db.Column(db.Boolean, default=True)
    failed_logins = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    company = db.Column(db.String(120))
    address = db.Column(db.String(250))
    city = db.Column(db.String(80))
    state = db.Column(db.String(80))
    status = db.Column(db.String(30), default="Active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    company = db.Column(db.String(120))
    source = db.Column(db.String(50), default="Website")
    status = db.Column(db.String(30), default="New")
    priority = db.Column(db.String(20), default="Medium")
    expected_value = db.Column(db.Float, default=0)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Opportunity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"))
    amount = db.Column(db.Float, nullable=False, default=1)
    probability = db.Column(db.Integer, default=50)
    stage = db.Column(db.String(30), default="Qualification")
    status = db.Column(db.String(20), default="Open")
    expected_close_date = db.Column(db.Date)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer", backref="opportunities")

class FollowUp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"))
    followup_date = db.Column(db.Date, nullable=False)
    followup_type = db.Column(db.String(30), default="Call")
    remarks = db.Column(db.String(500))
    status = db.Column(db.String(20), default="Planned")
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer")
    lead = db.relationship("Lead")

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(50), nullable=False)
    entity_name = db.Column(db.String(50), nullable=False)
    record_id = db.Column(db.Integer)
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))
    user = db.relationship("User")


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(30), nullable=False)  # Call, Meeting, Email, Task
    subject = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    activity_date = db.Column(db.DateTime, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"))
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(20), default="Open")
    customer = db.relationship("Customer")
    lead = db.relationship("Lead")
