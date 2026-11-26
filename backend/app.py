import os
import sqlite3
import sys
import time
import uuid
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ML_DIR = os.path.join(ROOT_DIR, "ml")
DB_PATH = os.path.join(ROOT_DIR, "co2_system.db")

if ML_DIR not in sys.path:
    sys.path.insert(0, ML_DIR)

from predict import predict_latest

app = FastAPI(title="Classroom CO2 Server")

latest_command = {
    "command_id": str(uuid.uuid4()),
    "fan_on": False,
    "threshold_ppm": 1000.0,
    "source": "init",
    "created_at": time.time(),
}


class TelemetryIn(BaseModel):
    seq_id: int
    timestamp: str
    co2_ppm: float
    temp_c: float
    humidity_pct: float
    pir_active: int
    auto_control: bool = True


class CommandIn(BaseModel):
    fan_on: bool
    threshold_ppm: float = 1000.0
    source: str = "manual_override"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seq_id INTEGER,
            timestamp TEXT,
            co2_ppm REAL,
            temp_c REAL,
            humidity_pct REAL,
            pir_active INTEGER,
            received_at REAL
        )
        """
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/forecast")
def get_forecast(threshold_ppm: Optional[float] = None):
    eff_threshold = (
        float(threshold_ppm)
        if threshold_ppm is not None
        else float(latest_command.get("threshold_ppm", 1000.0))
    )
    return predict_latest(db_path=DB_PATH, threshold_ppm=eff_threshold)


@app.post("/api/telemetry")
def receive_telemetry(data: TelemetryIn):
    global latest_command
    now_ts = time.time()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO telemetry (seq_id, timestamp, co2_ppm, temp_c, humidity_pct, pir_active, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.seq_id,
            data.timestamp,
            data.co2_ppm,
            data.temp_c,
            data.humidity_pct,
            data.pir_active,
            now_ts,
        ),
    )
    conn.commit()
    conn.close()

    threshold = float(latest_command.get("threshold_ppm", 1000.0))
    forecast = predict_latest(db_path=DB_PATH, threshold_ppm=threshold)

    # Không ghi đè nếu người dùng vừa bấm thủ công trên dashboard trong vòng 60 giây
    manual_recent = (
        latest_command.get("source") in ("streamlit_dashboard", "manual_override")
        and (now_ts - float(latest_command.get("created_at", 0.0))) < 60.0
    )

    if data.auto_control and not manual_recent and forecast.get("has_data"):
        desired_fan = bool(forecast["fan_on"])
        if desired_fan != bool(latest_command.get("fan_on")) or latest_command.get("source") != "ml_auto":
            latest_command = {
                "command_id": str(uuid.uuid4()),
                "fan_on": desired_fan,
                "threshold_ppm": threshold,
                "source": "ml_auto",
                "created_at": now_ts,
            }

    return {
        "status": "ok",
        "seq_id": data.seq_id,
        "forecast": forecast,
        "command": latest_command,
    }


@app.get("/api/command")
def get_command():
    return latest_command


@app.post("/api/command")
def set_command(cmd: CommandIn):
    global latest_command
    latest_command = {
        "command_id": str(uuid.uuid4()),
        "fan_on": cmd.fan_on,
        "threshold_ppm": cmd.threshold_ppm,
        "source": cmd.source,
        "created_at": time.time(),
    }
    return {"status": "updated", "command": latest_command}
