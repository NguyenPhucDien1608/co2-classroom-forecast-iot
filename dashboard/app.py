import os
import sqlite3
import sys
import time
from datetime import timedelta
import pandas as pd
import requests
import streamlit as st

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ML_DIR = os.path.join(ROOT_DIR, "ml")
DB_PATH = os.path.join(ROOT_DIR, "co2_system.db")
SERVER_URL = "http://127.0.0.1:8000"

if ML_DIR not in sys.path:
    sys.path.insert(0, ML_DIR)

from predict import predict_latest

st.set_page_config(
    page_title="Giám sát & Dự báo CO2 Phòng học",
    page_icon="🌬️",
    layout="wide",
)

st.title("Giám sát CO2 phòng học & điều khiển thông gió")

with st.sidebar:
    st.header("Cấu hình")
    server_url = st.text_input("Địa chỉ FastAPI", value=SERVER_URL)
    threshold_ppm = st.number_input(
        "Ngưỡng cảnh báo CO2 (ppm)", min_value=600, max_value=2500, value=1000, step=50
    )
    auto_refresh = st.checkbox("Tự động làm mới (5s)", value=False)
    if st.button("Làm mới ngay"):
        st.rerun()


def load_recent_telemetry(db_path: str, limit: int = 200) -> pd.DataFrame:
    if not os.path.exists(db_path):
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        f"""
        SELECT seq_id, timestamp, co2_ppm, temp_c, humidity_pct, pir_active
        FROM telemetry
        ORDER BY id DESC
        LIMIT {int(limit)}
        """,
        conn,
    )
    conn.close()
    if df.empty:
        return df
    df["dt"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)


forecast = predict_latest(db_path=DB_PATH, threshold_ppm=float(threshold_ppm))
df_hist = load_recent_telemetry(DB_PATH, limit=200)

try:
    cmd_state = requests.get(f"{server_url.rstrip('/')}/api/command", timeout=3).json()
except Exception as e:
    cmd_state = {"fan_on": False, "source": f"offline ({e})", "threshold_ppm": threshold_ppm}

c1, c2, c3, c4 = st.columns(4)
if forecast.get("has_data"):
    co2_now = forecast["co2_now"]
    delta_15 = round(forecast["pred_15m"] - co2_now, 1)
    delta_30 = round(forecast["pred_30m"] - co2_now, 1)
    c1.metric("CO2 hiện tại", f"{co2_now:.0f} ppm")
    c2.metric("Dự báo +15 phút", f"{forecast['pred_15m']:.0f} ppm", f"{delta_15:+.1f} ppm")
    c3.metric("Dự báo +30 phút", f"{forecast['pred_30m']:.0f} ppm", f"{delta_30:+.1f} ppm")
    c4.metric(
        "Trạng thái quạt",
        "ĐANG BẬT" if cmd_state.get("fan_on") else "ĐANG TẮT",
        f"PIR: {'Có người' if forecast.get('pir_active') == 1 else 'Trống'}",
    )
    st.info(f"**Khuyến nghị mô hình:** {forecast.get('reason', '')}")
else:
    c1.metric("CO2 hiện tại", "Chưa có dữ liệu")
    c2.metric("Dự báo +15 phút", "--")
    c3.metric("Dự báo +30 phút", "--")
    c4.metric("Trạng thái quạt", "ĐANG BẬT" if cmd_state.get("fan_on") else "ĐANG TẮT")
    st.warning("Chưa có dữ liệu trong SQLite. Hãy chạy `py scripts/mock_sensor.py` để gửi dữ liệu mẫu.")

st.divider()

st.subheader("Diễn biến CO2 & mốc dự báo tương lai")
if not df_hist.empty:
    chart_df = df_hist.set_index("dt")[["co2_ppm"]].rename(columns={"co2_ppm": "CO2 đo được (ppm)"})
    if forecast.get("has_data"):
        last_dt = df_hist["dt"].iloc[-1]
        pred_pts = pd.DataFrame(
            {
                "Dự báo ML (ppm)": [forecast["pred_15m"], forecast["pred_30m"]],
            },
            index=[last_dt + timedelta(minutes=15), last_dt + timedelta(minutes=30)],
        )
        chart_df = pd.concat([chart_df, pred_pts], axis=0)
    st.line_chart(chart_df)
else:
    st.write("Chưa có dữ liệu để vẽ biểu đồ.")

st.divider()

st.subheader("Điều khiển quạt thông gió")
col_on, col_off, col_info = st.columns([1, 1, 3])


def send_fan_command(fan_on: bool):
    try:
        res = requests.post(
            f"{server_url.rstrip('/')}/api/command",
            json={
                "fan_on": fan_on,
                "threshold_ppm": float(threshold_ppm),
                "source": "streamlit_dashboard",
            },
            timeout=5,
        )
        if res.status_code == 200:
            st.success(f"Đã gửi lệnh quạt: {'BẬT' if fan_on else 'TẮT'}")
            st.rerun()
        else:
            st.error(f"Lỗi cập nhật lệnh: {res.status_code}")
    except Exception as e:
        st.error(f"Không kết nối được tới FastAPI: {e}")


with col_on:
    if st.button("Bật quạt", type="primary", use_container_width=True):
        send_fan_command(True)

with col_off:
    if st.button("Tắt quạt", use_container_width=True):
        send_fan_command(False)

with col_info:
    st.caption(
        f"Lệnh hiện tại trên server: `fan_on={cmd_state.get('fan_on')}` | "
        f"Nguồn: `{cmd_state.get('source')}`"
    )

with st.expander("Xem bảng dữ liệu cảm biến gần nhất"):
    if not df_hist.empty:
        st.dataframe(df_hist.tail(20), use_container_width=True)
    else:
        st.write("Trống.")

if auto_refresh:
    time.sleep(5)
    st.rerun()
