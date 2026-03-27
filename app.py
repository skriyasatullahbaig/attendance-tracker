from flask import Flask, render_template, redirect, url_for, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from flask import Flask, render_template, redirect, url_for, request, session, flash
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask import send_file
from io import BytesIO
import calendar
from sqlalchemy import func
import os
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors

app = Flask(__name__)

# =====================
# Config
# =====================
app.config['SECRET_KEY'] = 'attendance-secret-key'

# Ensure instance folder exists
if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

# Absolute DB path (Windows-safe)
db_path = os.path.join(app.instance_path, "database.db")
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# =====================
# Database Model
# =====================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin / worker 

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    worker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)

    shift_type = db.Column(db.String(20), nullable=False)  # full / extended
    work_days = db.Column(db.Float, nullable=False)

    notes = db.Column(db.String(300))

    worker = db.relationship('User')


# =====================
# Routes
# =====================
@app.route("/")
def login():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    email = request.form["email"]
    password = request.form["password"]

    user = User.query.filter_by(email=email).first()

    if user and check_password_hash(user.password, password):
        session["user_id"] = user.id
        session["user_role"] = user.role
        session["user_name"] = user.name

        if user.role == "admin":
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("worker_dashboard"))

    return "Invalid email or password"


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with this email already exists. Please sign in.", "error")
            return redirect(url_for("signup"))

        hashed_password = generate_password_hash(password)

        user = User(
            name=name,
            email=email,
            password=hashed_password,
            role=role
        )

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Email already registered. Please sign in.", "error")
            return redirect(url_for("signup"))

        # ✅ SUCCESS MESSAGE
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


from sqlalchemy import func
from datetime import datetime
import calendar

@app.route("/admin/dashboard")
def admin_dashboard():
    if "user_role" not in session or session["user_role"] != "admin":
        return redirect(url_for("login"))

    # current month
    today = datetime.today()
    month = today.month
    year = today.year

    start_date = datetime(year, month, 1).date()
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day).date()

    # all workers (for dropdown)
    workers = User.query.filter_by(role="worker").all()

    # ================= WORKERS SUMMARY (Monthly total) =================
    workers_summary = []

    for worker in workers:
        total = db.session.query(func.sum(Attendance.work_days)).filter(
            Attendance.worker_id == worker.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).scalar()

        if total is None:
            total = 0

        workers_summary.append({
            "name": worker.name,
            "email": worker.email,
            "total_days": round(total, 2)
        })

    # ================= ALL ATTENDANCE RECORDS =================
    records = Attendance.query.order_by(Attendance.date.desc()).all()

    return render_template(
        "admin_dashboard.html",
        name=session["user_name"],
        workers=workers,
        workers_summary=workers_summary,
        records=records
    )




@app.route("/worker/dashboard")
def worker_dashboard():
    if "user_role" not in session or session["user_role"] != "worker":
        return redirect(url_for("login"))

    worker_id = session["user_id"]

    # Get selected month (from URL)
    today = datetime.today()

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    if month is None:
        month = today.month

    if year is None:
        year = today.year

    # month start & end
    start_date = datetime(year, month, 1).date()
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day).date()

    # Get attendance of that month only
    records = Attendance.query.filter(
        Attendance.worker_id == worker_id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).order_by(Attendance.date).all()

    # ====== Calculations ======
    # ====== Calculations ======
    total_days = sum(r.work_days for r in records)

    full_days = sum(1 for r in records if r.shift_type == "full")

    extended_days = sum(1 for r in records if r.shift_type == "extended")

    half_days = sum(1 for r in records if r.shift_type == "half")

    sunday_days = sum(1 for r in records if r.shift_type == "sunday")
    
    absent_days = sum(1 for r in records if r.shift_type == "absent")

    month_name = calendar.month_name[month]
    # For dropdown months
    months = [
    (1,"January"), (2,"February"), (3,"March"), (4,"April"),
    (5,"May"), (6,"June"), (7,"July"), (8,"August"),
    (9,"September"), (10,"October"), (11,"November"), (12,"December")
    ]


    return render_template(
    "worker_dashboard.html",
    name=session["user_name"],
    records=records,
    total_days=total_days,
    full_days=full_days,
    extended_days=extended_days,
    half_days=half_days,
    sunday_days=sunday_days,
    absent_days=absent_days,
    month_name=month_name,
    year=year,
    record_count=len(records),
    months=months,
    selected_month=month
)


from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask import send_file
from io import BytesIO
import calendar
from datetime import datetime

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

@app.route("/download_attendance")
def download_attendance():

    if "user_role" not in session or session["user_role"] != "worker":
        return redirect(url_for("login"))

    worker_id = session["user_id"]
    worker_name = session["user_name"]

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    today = datetime.today()

    if month is None:
        month = today.month
    if year is None:
        year = today.year

    start_date = datetime(year, month, 1).date()
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day).date()

    records = Attendance.query.filter(
        Attendance.worker_id == worker_id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).order_by(Attendance.date).all()

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer, pagesize=A4)

    styles = getSampleStyleSheet()
    elements = []

    month_name = calendar.month_name[month]

    # Title
    elements.append(Paragraph("<b>Attendance Report</b>", styles['Title']))
    elements.append(Spacer(1, 20))

    elements.append(Paragraph(f"Worker Name : {worker_name}", styles['Normal']))
    elements.append(Paragraph(f"Month : {month_name} {year}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # ================= TABLE DATA =================
    data = [["Date", "Day", "Shift", "Work Days", "Notes"]]

    total_work_days = 0

    if records:
        for r in records:

            day = r.date.strftime("%A")

            if r.shift_type == "full":
                shift = "Full Day"
            elif r.shift_type == "extended":
                shift = "Extended"
            elif r.shift_type == "half":
                shift = "Half Day"
            elif r.shift_type == "sunday":
                shift = "Sunday"
            elif r.shift_type == "absent":
                shift = "Absent"

            data.append([
                r.date.strftime("%d-%m-%Y"),
                day,
                shift,
                r.work_days,
                r.notes if r.notes else "-"
            ])

            total_work_days += r.work_days

    else:
        data.append(["-", "-", "No attendance records", "-", "-"])

    # ================= TABLE =================
    table = Table(data, colWidths=[90, 90, 100, 80, 150])

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("ALIGN", (3,1), (3,-1), "CENTER"),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # ================= TOTAL =================
    elements.append(Paragraph(
        f"<b>Total Work Days : {round(total_work_days,2)}</b>",
        styles['Normal']
    ))

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"attendance_{month_name}_{year}.pdf",
        mimetype="application/pdf"
    )





@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    if "user_role" not in session or session["user_role"] != "admin":
        return redirect(url_for("login"))

    worker_id = request.form["worker_id"]
    date_str = request.form["date"]
    shift_type = request.form["shift_type"]
    notes = request.form.get("notes")

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

    # prevent duplicate attendance
    existing = Attendance.query.filter_by(worker_id=worker_id, date=date_obj).first()
    if existing:
        return "Attendance already marked for this worker on this date."

    if shift_type == "full":
        work_days = 1.0

    elif shift_type == "extended":
        work_days = 1.5

    elif shift_type == "half":
        work_days = 0.5

    elif shift_type == "sunday":
        work_days = 1.0
    
    elif shift_type == "absent":
        work_days = 0.0

    record = Attendance(
        worker_id=worker_id,
        date=date_obj,
        shift_type=shift_type,
        work_days=work_days,
        notes=notes
    )

    db.session.add(record)
    db.session.commit()
    flash("Attendance marked successfully!", "success")
    return redirect(url_for("admin_dashboard"))




@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =====================
# Run App
# =====================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=10000)

