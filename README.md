# Website quản lý sinh viên - bản nâng cấp dashboard

## Công nghệ
- Python 3.12
- Flask: định tuyến và xử lý backend
- SQLite: lưu dữ liệu sinh viên, môn học, điểm, học phí
- Waitress: phục vụ ứng dụng WSGI
- Chart.js (tải từ CDN): biểu đồ học phí, kết quả học tập, sinh viên theo lớp
- Dockerfile và Docker Compose: đóng gói và triển khai

## Chạy bằng Docker
Mở PowerShell tại thư mục có `compose.yaml`:
```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f web
```
Truy cập http://localhost:5000

Dừng ứng dụng:
```powershell
docker compose down
```
Dữ liệu SQLite được lưu trong named volume `student_data`, vì vậy lệnh `docker compose down` thông thường không xóa volume.

## Chạy trực tiếp trên Windows (tùy chọn)
Tạo môi trường ảo rồi cài thư viện:
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```
Truy cập http://127.0.0.1:5000

## Dashboard mới
- Thẻ KPI: tổng sinh viên, môn học, bản ghi điểm, học phí còn nợ.
- Biểu đồ học phí phải đóng/đã đóng/còn nợ.
- Biểu đồ phân loại kết quả học tập.
- Biểu đồ số sinh viên theo lớp.
- Dữ liệu biểu đồ được truy vấn từ SQLite, không phải số liệu minh họa cố định.

## Ghi chú về thư viện
Không thêm 20 thư viện Python chỉ để làm đẹp giao diện vì điều đó làm image lớn hơn, tăng thời gian cài đặt và rủi ro xung đột phụ thuộc. Phiên bản này giữ backend gọn (Flask + Waitress) và sử dụng Chart.js cho biểu đồ; phần CSS thuần được cải tiến để không cần thêm framework frontend lớn.
Chart.js được tải từ CDN nên trình duyệt cần Internet để hiển thị biểu đồ. Nếu cần demo ngoại tuyến, có thể tải Chart.js vào thư mục `static/` và phục vụ nội bộ.
