from datetime import datetime, date, timedelta
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_
from models import db, User, Customer, Lead, Opportunity, FollowUp, AuditLog

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-before-deployment"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str((app.instance_path and (Path(app.instance_path) / "crm.db")))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db.init_app(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
app.jinja_env.globals["today"] = lambda: date.today().isoformat()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def audit(action, entity, record_id=None, old_value=None, new_value=None):
    db.session.add(AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action, entity_name=entity, record_id=record_id,
        old_value=str(old_value)[:2000] if old_value is not None else None,
        new_value=str(new_value)[:2000] if new_value is not None else None,
        ip_address=request.remote_addr
    ))

def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

def can_see(record_user_id):
    return current_user.role in ("Admin", "Manager") or record_user_id == current_user.id

def visible_customers():
    q = Customer.query
    if current_user.role == "SalesExecutive":
        q = q.filter_by(created_by=current_user.id)
    return q

def visible_leads():
    q = Lead.query
    if current_user.role == "SalesExecutive":
        q = q.filter_by(assigned_to=current_user.id)
    return q

def visible_opportunities():
    q = Opportunity.query
    if current_user.role == "SalesExecutive":
        q = q.filter_by(assigned_to=current_user.id)
    return q

def visible_followups():
    q = FollowUp.query
    if current_user.role == "SalesExecutive":
        q = q.filter_by(assigned_to=current_user.id)
    return q

@app.route("/")
def home():
    return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name, valid email and a password of at least 8 characters.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
        else:
            user = User(name=name, email=email, role="SalesExecutive")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            audit("REGISTER", "User", user.id, new_value=email)
            db.session.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        now = datetime.utcnow()
        if user and user.locked_until and user.locked_until > now:
            flash("Account temporarily locked. Try again later.", "danger")
        elif user and user.active and user.check_password(password):
            user.failed_logins = 0
            user.locked_until = None
            db.session.commit()
            login_user(user)
            audit("LOGIN_SUCCESS", "User", user.id)
            db.session.commit()
            return redirect(url_for("dashboard"))
        else:
            if user:
                user.failed_logins = (user.failed_logins or 0) + 1
                if user.failed_logins >= 5:
                    user.locked_until = now + timedelta(minutes=10)
                db.session.commit()
            audit("LOGIN_FAILED", "User", user.id if user else None)
            db.session.commit()
            flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("LOGOUT", "User", current_user.id)
    db.session.commit()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    customers = visible_customers()
    leads = visible_leads()
    opps = visible_opportunities()
    followups = visible_followups()
    lead_rows = leads.all()
    opp_rows = opps.all()
    cards = {
        "customers": customers.count(),
        "leads": len(lead_rows),
        "open_leads": sum(1 for x in lead_rows if x.status not in ("Lost", "Converted", "Unqualified")),
        "opportunities": len(opp_rows),
        "open_opportunities": sum(1 for x in opp_rows if x.status == "Open"),
        "won": sum(1 for x in opp_rows if x.status == "Won"),
        "lost": sum(1 for x in opp_rows if x.status == "Lost"),
        "pipeline": sum(x.amount * x.probability / 100 for x in opp_rows if x.status == "Open"),
        "pending": followups.filter_by(status="Planned").count()
    }
    lead_labels = ["New", "Contacted", "Qualified", "Lost", "Converted"]
    lead_values = [sum(1 for x in lead_rows if x.status == s) for s in lead_labels]
    stage_labels = ["Qualification", "Proposal", "Negotiation", "Won", "Lost"]
    stage_values = [sum(1 for x in opp_rows if x.stage == s) for s in stage_labels]
    return render_template("dashboard.html", cards=cards, lead_labels=lead_labels,
                           lead_values=lead_values, stage_labels=stage_labels, stage_values=stage_values)

@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        if not name or "@" not in email or len(phone) < 7:
            flash("Name, valid email and phone (at least 7 digits) are required.", "danger")
        elif Customer.query.filter(or_(Customer.email == email, Customer.phone == phone)).first():
            flash("Customer email or phone already exists.", "danger")
        else:
            c = Customer(code=f"CUS-{int(datetime.utcnow().timestamp())}", name=name, email=email,
                         phone=phone, company=request.form.get("company", "").strip(),
                         address=request.form.get("address", "").strip(),
                         city=request.form.get("city", "").strip(), state=request.form.get("state", "").strip(),
                         created_by=current_user.id)
            db.session.add(c); db.session.flush()
            audit("CREATE", "Customer", c.id, new_value=name)
            db.session.commit()
            flash("Customer added successfully.", "success")
            return redirect(url_for("customers"))
    search = request.args.get("q", "").strip()
    q = visible_customers()
    if search:
        q = q.filter(or_(Customer.name.ilike(f"%{search}%"), Customer.email.ilike(f"%{search}%"),
                         Customer.phone.ilike(f"%{search}%"), Customer.company.ilike(f"%{search}%")))
    return render_template("customers.html", rows=q.order_by(Customer.created_at.desc()).all())

@app.post("/customers/<int:record_id>/delete")
@login_required
def delete_customer(record_id):
    c = visible_customers().filter_by(id=record_id).first_or_404()
    audit("DELETE", "Customer", c.id, old_value=c.name)
    db.session.delete(c); db.session.commit()
    flash("Customer deleted.", "success")
    return redirect(url_for("customers"))

@app.route("/leads", methods=["GET", "POST"])
@login_required
def leads():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Lead name is required.", "danger")
        else:
            lead = Lead(code=f"LEAD-{int(datetime.utcnow().timestamp())}", name=name,
                        email=request.form.get("email", "").strip(), phone=request.form.get("phone", "").strip(),
                        company=request.form.get("company", "").strip(), source=request.form.get("source", "Website"),
                        status=request.form.get("status", "New"), priority=request.form.get("priority", "Medium"),
                        expected_value=float(request.form.get("expected_value") or 0),
                        assigned_to=current_user.id if current_user.role == "SalesExecutive" else int(request.form.get("assigned_to") or current_user.id))
            db.session.add(lead); db.session.flush(); audit("CREATE", "Lead", lead.id, new_value=name)
            db.session.commit(); flash("Lead added.", "success"); return redirect(url_for("leads"))
    search = request.args.get("q", "").strip()
    q = visible_leads()
    if search:
        q = q.filter(or_(Lead.name.ilike(f"%{search}%"), Lead.company.ilike(f"%{search}%"), Lead.status.ilike(f"%{search}%")))
    return render_template("leads.html", rows=q.order_by(Lead.created_at.desc()).all(),
                           users=User.query.filter_by(active=True).all())

@app.post("/leads/<int:record_id>/delete")
@login_required
def delete_lead(record_id):
    row = visible_leads().filter_by(id=record_id).first_or_404()
    audit("DELETE", "Lead", row.id, old_value=row.name)
    db.session.delete(row); db.session.commit(); flash("Lead deleted.", "success")
    return redirect(url_for("leads"))

@app.route("/opportunities", methods=["GET", "POST"])
@login_required
def opportunities():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            amount = float(request.form.get("amount", "0"))
            probability = int(request.form.get("probability", "50"))
            close_date = date.fromisoformat(request.form.get("expected_close_date", ""))
            if not name or amount <= 0 or not 0 <= probability <= 100:
                raise ValueError()
            if close_date < date.today() and request.form.get("status", "Open") == "Open":
                flash("Expected close date cannot be in the past for an open opportunity.", "danger")
                raise ValueError()
            row = Opportunity(name=name, amount=amount, probability=probability,
                stage=request.form.get("stage", "Qualification"), status=request.form.get("status", "Open"),
                expected_close_date=close_date,
                customer_id=int(request.form.get("customer_id")) if request.form.get("customer_id") else None,
                assigned_to=current_user.id if current_user.role == "SalesExecutive" else int(request.form.get("assigned_to") or current_user.id))
            db.session.add(row); db.session.flush(); audit("CREATE", "Opportunity", row.id, new_value=name)
            db.session.commit(); flash("Opportunity added.", "success"); return redirect(url_for("opportunities"))
        except (ValueError, TypeError):
            db.session.rollback()
            if not any("past" in str(x) for x in []):
                flash("Check opportunity name, amount, probability and expected close date.", "danger")
    return render_template("opportunities.html", rows=visible_opportunities().order_by(Opportunity.created_at.desc()).all(),
                           customers=visible_customers().all(), users=User.query.filter_by(active=True).all())

@app.post("/opportunities/<int:record_id>/delete")
@login_required
def delete_opportunity(record_id):
    row = visible_opportunities().filter_by(id=record_id).first_or_404()
    audit("DELETE", "Opportunity", row.id, old_value=row.name)
    db.session.delete(row); db.session.commit(); flash("Opportunity deleted.", "success")
    return redirect(url_for("opportunities"))

@app.route("/followups", methods=["GET", "POST"])
@login_required
def followups():
    if request.method == "POST":
        try:
            fdate = date.fromisoformat(request.form.get("followup_date", ""))
            if fdate < date.today():
                raise ValueError("past")
            row = FollowUp(followup_date=fdate, followup_type=request.form.get("followup_type", "Call"),
                remarks=request.form.get("remarks", "").strip(), status="Planned",
                customer_id=int(request.form.get("customer_id")) if request.form.get("customer_id") else None,
                lead_id=int(request.form.get("lead_id")) if request.form.get("lead_id") else None,
                assigned_to=current_user.id)
            if not row.customer_id and not row.lead_id:
                raise ValueError("related")
            db.session.add(row); db.session.flush(); audit("CREATE", "FollowUp", row.id, new_value=row.followup_type)
            db.session.commit(); flash("Follow-up scheduled.", "success"); return redirect(url_for("followups"))
        except ValueError:
            db.session.rollback(); flash("Choose a customer or lead and a date today or later.", "danger")
    return render_template("followups.html", rows=visible_followups().order_by(FollowUp.followup_date).all(),
                           customers=visible_customers().all(), leads=visible_leads().all())

@app.post("/followups/<int:record_id>/complete")
@login_required
def complete_followup(record_id):
    row = visible_followups().filter_by(id=record_id).first_or_404()
    row.status = "Completed"; audit("UPDATE", "FollowUp", row.id, new_value="Completed")
    db.session.commit(); flash("Follow-up marked completed.", "success")
    return redirect(url_for("followups"))

@app.route("/users", methods=["GET", "POST"])
@roles_required("Admin")
def users():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "SalesExecutive")
        if not name or "@" not in email or len(password) < 8 or role not in ("Admin", "Manager", "SalesExecutive"):
            flash("Enter valid details and a password of at least 8 characters.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Email already exists.", "danger")
        else:
            u = User(name=name, email=email, role=role); u.set_password(password)
            db.session.add(u); db.session.flush(); audit("CREATE", "User", u.id, new_value=f"{email} / {role}")
            db.session.commit(); flash("User created.", "success"); return redirect(url_for("users"))
    return render_template("users.html", rows=User.query.order_by(User.created_at.desc()).all())

@app.post("/users/<int:user_id>/toggle")
@roles_required("Admin")
def toggle_user(user_id):
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("You cannot deactivate your own account.", "warning")
    else:
        u.active = not u.active; audit("UPDATE", "User", u.id, new_value=f"active={u.active}")
        db.session.commit(); flash("User status updated.", "success")
    return redirect(url_for("users"))

@app.route("/audit-logs")
@roles_required("Admin")
def audit_logs():
    rows = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(250).all()
    return render_template("audit_logs.html", rows=rows)

@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html", customers=visible_customers().count(),
        leads=visible_leads().count(), opportunities=visible_opportunities().count(),
        won=visible_opportunities().filter_by(status="Won").count(),
        pipeline=sum(x.amount*x.probability/100 for x in visible_opportunities().filter_by(status="Open").all()))

# JSON REST API. Login is required; Sales Executives see only their assigned/created records.
@app.route("/api/customers", methods=["GET", "POST"])
@login_required
def api_customers():
    if request.method == "GET":
        return jsonify([{"id":x.id,"name":x.name,"email":x.email,"phone":x.phone,"company":x.company}
                        for x in visible_customers().all()])
    data = request.get_json(silent=True) or {}
    if not data.get("name") or "@" not in data.get("email", "") or len(data.get("phone", "")) < 7:
        return jsonify({"error":"name, valid email and phone are required"}), 400
    if Customer.query.filter(or_(Customer.email==data["email"], Customer.phone==data["phone"])).first():
        return jsonify({"error":"email or phone already exists"}), 409
    row = Customer(name=data["name"], email=data["email"], phone=data["phone"],
                   company=data.get("company",""), created_by=current_user.id)
    db.session.add(row); db.session.flush(); audit("API_CREATE","Customer",row.id)
    db.session.commit()
    return jsonify({"id":row.id,"message":"created"}), 201

@app.route("/api/customers/<int:record_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def api_customer_detail(record_id):
    row = visible_customers().filter_by(id=record_id).first_or_404()
    if request.method == "GET":
        return jsonify({"id":row.id,"name":row.name,"email":row.email,"phone":row.phone,"company":row.company})
    if request.method == "DELETE":
        audit("API_DELETE","Customer",row.id); db.session.delete(row); db.session.commit()
        return jsonify({"message":"deleted"})
    data = request.get_json(silent=True) or {}
    if not data.get("name") or "@" not in data.get("email","") or len(data.get("phone","")) < 7:
        return jsonify({"error":"invalid customer data"}), 400
    row.name=data["name"]; row.email=data["email"]; row.phone=data["phone"]; row.company=data.get("company","")
    audit("API_UPDATE","Customer",row.id); db.session.commit()
    return jsonify({"message":"updated"})

@app.route("/api/leads", methods=["GET", "POST"])
@login_required
def api_leads():
    if request.method == "GET":
        return jsonify([{"id":x.id,"name":x.name,"status":x.status,"company":x.company} for x in visible_leads().all()])
    data=request.get_json(silent=True) or {}
    if not data.get("name"): return jsonify({"error":"name is required"}),400
    row=Lead(name=data["name"],company=data.get("company",""),status=data.get("status","New"),assigned_to=current_user.id)
    db.session.add(row); db.session.flush(); audit("API_CREATE","Lead",row.id); db.session.commit()
    return jsonify({"id":row.id,"message":"created"}),201

@app.route("/api/opportunities", methods=["GET", "POST"])
@login_required
def api_opportunities():
    if request.method == "GET":
        return jsonify([{"id":x.id,"name":x.name,"amount":x.amount,"probability":x.probability,"stage":x.stage}
                        for x in visible_opportunities().all()])
    data=request.get_json(silent=True) or {}
    try:
        amount=float(data.get("amount",0)); probability=int(data.get("probability",50))
        if not data.get("name") or amount<=0 or not 0<=probability<=100: raise ValueError()
    except (ValueError,TypeError):
        return jsonify({"error":"name, positive amount and probability 0-100 are required"}),400
    row=Opportunity(name=data["name"],amount=amount,probability=probability,assigned_to=current_user.id)
    db.session.add(row); db.session.flush(); audit("API_CREATE","Opportunity",row.id); db.session.commit()
    return jsonify({"id":row.id,"message":"created"}),201

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403

@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The requested page or record was not found."), 404

def initialize_database():
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email="admin@acxiomcrm.local").first():
            admin=User(name="System Admin",email="admin@acxiomcrm.local",role="Admin")
            admin.set_password("Admin@123")
            db.session.add(admin); db.session.commit()

if __name__ == "__main__":
    initialize_database()
    app.run(debug=True)
