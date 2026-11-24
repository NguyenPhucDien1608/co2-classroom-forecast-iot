# Nhóm 10 — Dự báo nồng độ CO2 phòng học và tự động thông gió chủ động
**English Title:** Forecasting Classroom CO2 Levels and Proactive Automatic Ventilation  
**Môn học:** Lập trình Hệ thống nhúng và mạng kết nối vạn vật (71ITNW30403)  
**Giảng viên hướng dẫn:** Nguyễn Trương Khang  
**Thời gian thực hiện:** 2 tuần

## Thành viên nhóm
1. Đỗ Lê Trọng Hiếu — MSSV: 2474802010112 (Nhóm trưởng)
2. Trần Hoàng Thông — MSSV: 2474802010375
3. Nguyễn Lê Trọng — MSSV: 2375106052637
4. Nguyễn Trọng Nhân — MSSV: 2474802010406

## Kiến trúc tổng quan
- **Thiết bị biên & cảm biến:** ESP32 (MicroPython), MH-Z19C (UART), DHT11, PIR HC-SR501, LCD 16x2 I2C, Relay 5V (cách ly Opto) điều khiển quạt mini 12V qua GPIO 26 *(quạt mini chỉ minh họa vòng điều khiển trên mô hình thử nghiệm)*.
- **Truyền thông:** Gửi dữ liệu JSON qua HTTP POST mỗi 60 giây (kèm ghi dự phòng lên Flash); hỏi lệnh điều khiển quạt qua HTTP GET mỗi 3–5 giây.
- **Máy chủ & lưu trữ:** FastAPI + SQLite (xuất CSV).
- **Mô hình & giao diện:** Hồi quy chuỗi thời gian dự báo CO2 tại `t + 15` và `t + 30` phút bằng `scikit-learn` (so sánh với Persistence và Linear Extrapolation baseline), hiển thị qua Streamlit.

## Lưu ý bảo mật
- Không đẩy mật khẩu Wi-Fi, token hoặc file cấu hình cá nhân (`config.py`, `esp32/config.py`, `.env`) lên repository.
