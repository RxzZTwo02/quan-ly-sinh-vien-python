import os
import secrets
import sqlite3
from pathlib import Path

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from waitress import serve


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Khi chạy trực tiếp: lưu trong thư mục data của dự án.
# Khi chạy Docker: giá trị này được đặt thành /app/data.
DATA_DIR = Path(
    os.environ.get(
        "DATA_DIR",
        str(Path(__file__).resolve().parent / "data"),
    )
)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "students.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    connection = get_connection()
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_code TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    email TEXT NOT NULL
                )
                """
            )
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
    connection = get_connection()

    try:
        students = connection.execute(
            """
            SELECT * FROM students
            WHERE student_code LIKE ?
               OR full_name LIKE ?
               OR class_name LIKE ?
            ORDER BY id DESC
            """,
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()

        editing = None
        if edit_id is not None:
            editing = connection.execute(
                "SELECT * FROM students WHERE id = ?",
                (edit_id,),
            ).fetchone()

        total = connection.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0]
    finally:
        connection.close()

    return render_template(
        "index.html",
        students=students,
        editing=editing,
        keyword=keyword,
        total=total,
        message=request.args.get("message", ""),
        error=request.args.get("error", ""),
    )


@app.post("/save")
def save_student():
    student_id = request.form.get("id", "").strip()
    student_code = request.form.get("student_code", "").strip().upper()
    full_name = request.form.get("full_name", "").strip()
    class_name = request.form.get("class_name", "").strip()
    email = request.form.get("email", "").strip()

    if not all([student_code, full_name, class_name, email]):
        return redirect(url_for("index", error="Vui lòng nhập đủ thông tin."))

    if (
        len(student_code) > 20
        or len(full_name) > 100
        or len(class_name) > 50
        or len(email) > 120
        or "@" not in email
    ):
        return redirect(url_for("index", error="Thông tin nhập không hợp lệ."))

    if student_id and not student_id.isdecimal():
        abort(400)

    connection = get_connection()
    try:
        with connection:
            if student_id:
                result = connection.execute(
                    """
                    UPDATE students
                    SET student_code = ?, full_name = ?,
                        class_name = ?, email = ?
                    WHERE id = ?
                    """,
                    (
                        student_code,
                        full_name,
                        class_name,
                        email,
                        int(student_id),
                    ),
                )
                if result.rowcount == 0:
                    abort(404)
                message = "Đã cập nhật sinh viên."
            else:
                connection.execute(
                    """
                    INSERT INTO students
                        (student_code, full_name, class_name, email)
                    VALUES (?, ?, ?, ?)
                    """,
                    (student_code, full_name, class_name, email),
                )
                message = "Đã thêm sinh viên."
    except sqlite3.IntegrityError:
        return redirect(url_for("index", error="Mã sinh viên đã tồn tại."))
    finally:
        connection.close()

    return redirect(url_for("index", message=message))


@app.post("/delete/<int:student_id>")
def delete_student(student_id):
    connection = get_connection()
    try:
        with connection:
            result = connection.execute(
                "DELETE FROM students WHERE id = ?",
                (student_id,),
            )
            if result.rowcount == 0:
                abort(404)
    finally:
        connection.close()

    return redirect(url_for("index", message="Đã xóa sinh viên."))


@app.get("/health")
def health():
    return {"status": "ok"}, 200


init_database()


if __name__ == "__main__":
    # Lắng nghe trên mọi giao diện mạng để nhận được kết nối qua Docker.
    serve(app, host="0.0.0.0", port=5000)