import random
import time
from datetime import datetime, timezone
import requests

SERVER_URL = "http://127.0.0.1:8000"


def send_sample(seq_id: int, co2_ppm: float, pir_active: int = 1):
    payload = {
        "seq_id": seq_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "co2_ppm": co2_ppm,
        "temp_c": round(random.uniform(25.0, 28.5), 1),
        "humidity_pct": round(random.uniform(55.0, 70.0), 1),
        "pir_active": pir_active,
    }
    res = requests.post(f"{SERVER_URL}/api/telemetry", json=payload, timeout=5)
    print("Gửi:", payload, "-> Phản hồi:", res.json())


if __name__ == "__main__":
    for i in range(1, 6):
        send_sample(seq_id=i, co2_ppm=650.0 + i * 80, pir_active=1)
        time.sleep(1)

    cmd = requests.get(f"{SERVER_URL}/api/command", timeout=5).json()
    print("Lệnh quạt hiện tại từ server:", cmd)
