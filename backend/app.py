import sqlite3
import time
import uuid
from fastapi import FastAPI
from pydantic import BaseModel

DB_PATH = "co2_system.db"
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


@app.post("/api/telemetry")
def receive_telemetry(data: TelemetryIn):
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
            time.time(),
        ),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "seq_id": data.seq_id}


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
