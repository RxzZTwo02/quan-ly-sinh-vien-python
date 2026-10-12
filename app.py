import os
import secrets
import sqlite3
from pathlib import Path
from flask import Flask, abort, redirect, render_template, request, session, url_for
from waitress import serve

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "students.db"

def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def init_database():
    connection = get_connection()
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                class_name TEXT NOT NULL,
                email TEXT NOT NULL
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_code TEXT NOT NULL UNIQUE,
                subject_name TEXT NOT NULL,
                credits INTEGER NOT NULL DEFAULT 3 CHECK (credits > 0)
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                semester TEXT NOT NULL,
                attendance REAL NOT NULL DEFAULT 0 CHECK(attendance BETWEEN 0 AND 10),
                midterm REAL NOT NULL DEFAULT 0 CHECK(midterm BETWEEN 0 AND 10),
                final REAL NOT NULL DEFAULT 0 CHECK(final BETWEEN 0 AND 10),
                UNIQUE(student_id, subject_id, semester),
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS tuition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                semester TEXT NOT NULL,
                amount_due REAL NOT NULL CHECK(amount_due >= 0),
                amount_paid REAL NOT NULL DEFAULT 0 CHECK(amount_paid >= 0),
                due_date TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                UNIQUE(student_id, semester),
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            )""")
    finally:
        connection.close()

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]
app.jinja_env.globals["csrf_token"] = csrf_token

@app.before_request
def check_csrf():
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        actual = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected, actual):
            abort(400, description="Phiên làm việc hết hạn. Hãy tải lại trang.")

@app.get("/")
def index():
    keyword = request.args.get("q", "").strip()
    edit_id = request.args.get("edit", type=int)
    conn = get_connection()
    try:
        students = conn.execute("""SELECT * FROM students
            WHERE student_code LIKE ? OR full_name LIKE ? OR class_name LIKE ?
            ORDER BY id DESC""", (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")).fetchall()
        editing = conn.execute("SELECT * FROM students WHERE id=?", (edit_id,)).fetchone() if edit_id else None
        subjects = conn.execute("SELECT * FROM subjects ORDER BY subject_name").fetchall()
        grades = conn.execute("""SELECT g.*, s.student_code, s.full_name, sub.subject_code, sub.subject_name,
            sub.credits, ROUND(g.attendance*0.1 + g.midterm*0.3 + g.final*0.6, 2) AS total
            FROM grades g JOIN students s ON s.id=g.student_id
            JOIN subjects sub ON sub.id=g.subject_id
            ORDER BY g.semester DESC, s.student_code, sub.subject_name""").fetchall()
        tuition = conn.execute("""SELECT t.*, s.student_code, s.full_name,
            MAX(t.amount_due-t.amount_paid, 0) AS balance
            FROM tuition t JOIN students s ON s.id=t.student_id
            ORDER BY t.semester DESC, s.student_code""").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        subject_count = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        grade_count = conn.execute("SELECT COUNT(*) FROM grades").fetchone()[0]
        tuition_balance = conn.execute("SELECT COALESCE(SUM(MAX(amount_due-amount_paid,0)),0) FROM tuition").fetchone()[0]
    finally:
        conn.close()
    return render_template("index.html", students=students, editing=editing, keyword=keyword,
        total=total, subjects=subjects, grades=grades, tuition=tuition,
        subject_count=subject_count, grade_count=grade_count, tuition_balance=tuition_balance,
        message=request.args.get("message", ""), error=request.args.get("error", ""))

@app.post("/save")
def save_student():
    student_id=request.form.get("id","").strip()
    student_code=request.form.get("student_code","").strip().upper()
    full_name=request.form.get("full_name","").strip()
    class_name=request.form.get("class_name","").strip()
    email=request.form.get("email","").strip()
    if not all([student_code,full_name,class_name,email]) or len(student_code)>20 or len(full_name)>100 or len(class_name)>50 or len(email)>120 or "@" not in email:
        return redirect(url_for("index", error="Vui lòng nhập đủ thông tin hợp lệ."))
    conn=get_connection()
    try:
        with conn:
            if student_id:
                if not student_id.isdecimal(): abort(400)
                result=conn.execute("UPDATE students SET student_code=?,full_name=?,class_name=?,email=? WHERE id=?",
                    (student_code,full_name,class_name,email,int(student_id)))
                if not result.rowcount: abort(404)
                message="Đã cập nhật sinh viên."
            else:
                conn.execute("INSERT INTO students(student_code,full_name,class_name,email) VALUES(?,?,?,?)",
                    (student_code,full_name,class_name,email))
                message="Đã thêm sinh viên."
    except sqlite3.IntegrityError:
        return redirect(url_for("index", error="Mã sinh viên đã tồn tại hoặc dữ liệu không hợp lệ."))
    finally: conn.close()
    return redirect(url_for("index",message=message))

@app.post("/delete/<int:student_id>")
def delete_student(student_id):
    conn=get_connection()
    try:
        with conn:
            result=conn.execute("DELETE FROM students WHERE id=?",(student_id,))
            if not result.rowcount: abort(404)
    finally: conn.close()
    return redirect(url_for("index",message="Đã xóa sinh viên và dữ liệu điểm/học phí liên quan."))

@app.post("/subjects/save")
def save_subject():
    code=request.form.get("subject_code","").strip().upper()
    name=request.form.get("subject_name","").strip()
    try: credits=int(request.form.get("credits","3"))
    except ValueError: credits=0
    if not code or not name or credits < 1 or credits > 10:
        return redirect(url_for("index",error="Môn học cần có mã, tên và số tín chỉ từ 1 đến 10."))
    conn=get_connection()
    try:
        with conn: conn.execute("INSERT INTO subjects(subject_code,subject_name,credits) VALUES(?,?,?)",(code,name,credits))
    except sqlite3.IntegrityError:
        return redirect(url_for("index",error="Mã môn học đã tồn tại."))
    finally: conn.close()
    return redirect(url_for("index",message="Đã thêm môn học."))

@app.post("/grades/save")
def save_grade():
    try:
        student_id=int(request.form["student_id"]); subject_id=int(request.form["subject_id"])
        semester=request.form["semester"].strip()
        attendance=float(request.form["attendance"]); midterm=float(request.form["midterm"]); final=float(request.form["final"])
        if not semester or any(x < 0 or x > 10 for x in [attendance,midterm,final]): raise ValueError()
    except (ValueError, KeyError):
        return redirect(url_for("index",error="Điểm phải nằm trong khoảng 0–10 và cần chọn sinh viên, môn học, học kỳ."))
    conn=get_connection()
    try:
        with conn:
            conn.execute("""INSERT INTO grades(student_id,subject_id,semester,attendance,midterm,final)
                VALUES(?,?,?,?,?,?) ON CONFLICT(student_id,subject_id,semester)
                DO UPDATE SET attendance=excluded.attendance, midterm=excluded.midterm, final=excluded.final""",
                (student_id,subject_id,semester,attendance,midterm,final))
    except sqlite3.IntegrityError:
        return redirect(url_for("index",error="Sinh viên hoặc môn học không tồn tại."))
    finally: conn.close()
    return redirect(url_for("index",message="Đã lưu điểm. Điểm tổng kết được tính theo 10% chuyên cần, 30% giữa kỳ, 60% cuối kỳ."))

@app.post("/tuition/save")
def save_tuition():
    try:
        student_id=int(request.form["student_id"]); semester=request.form["semester"].strip()
        due=float(request.form["amount_due"]); paid=float(request.form.get("amount_paid","0"))
        due_date=request.form.get("due_date","").strip(); note=request.form.get("note","").strip()
        if not semester or due < 0 or paid < 0 or paid > due: raise ValueError()
    except (ValueError,KeyError):
        return redirect(url_for("index",error="Học phí không hợp lệ; số đã đóng phải từ 0 đến số phải đóng."))
    conn=get_connection()
    try:
        with conn:
            conn.execute("""INSERT INTO tuition(student_id,semester,amount_due,amount_paid,due_date,note)
                VALUES(?,?,?,?,?,?) ON CONFLICT(student_id,semester) DO UPDATE SET
                amount_due=excluded.amount_due, amount_paid=excluded.amount_paid,
                due_date=excluded.due_date, note=excluded.note""",
                (student_id,semester,due,paid,due_date,note))
    except sqlite3.IntegrityError:
        return redirect(url_for("index",error="Sinh viên không tồn tại."))
    finally: conn.close()
    return redirect(url_for("index",message="Đã lưu thông tin học phí."))

@app.post("/grades/delete/<int:grade_id>")
def delete_grade(grade_id):
    conn=get_connection()
    try:
        with conn: conn.execute("DELETE FROM grades WHERE id=?",(grade_id,))
    finally: conn.close()
    return redirect(url_for("index",message="Đã xóa bản ghi điểm."))

@app.get("/health")
def health():
    return {"status":"ok"},200

init_database()
if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000)
