import time
import network
import ujson
import urequests
from machine import Pin, UART

try:
    import config as cfg
except ImportError:
    raise RuntimeError("Thiếu file esp32/config.py. Hãy copy từ esp32/config.py.example và cấu hình.")


pir = Pin(cfg.PIR_PIN, Pin.IN)
relay = Pin(cfg.RELAY_PIN, Pin.OUT)

uart = None
if not cfg.SIMULATE_SENSORS:
    uart = UART(
        cfg.MHZ19_UART_ID,
        baudrate=9600,
        tx=cfg.MHZ19_TX_PIN,
        rx=cfg.MHZ19_RX_PIN,
        timeout=200,
    )

_sim_seq = 0
_sim_co2 = 680.0
_last_applied_command_id = None


def set_fan_state(fan_on: bool):
    if cfg.RELAY_ACTIVE_HIGH:
        relay.value(1 if fan_on else 0)
    else:
        relay.value(0 if fan_on else 1)


def connect_wifi(timeout_sec: int = 20) -> bool:
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True

    print("Đang kết nối Wi-Fi:", cfg.WIFI_SSID)
    wlan.connect(cfg.WIFI_SSID, cfg.WIFI_PASSWORD)

    deadline = time.time() + timeout_sec
    while not wlan.isconnected() and time.time() < deadline:
        time.sleep(0.5)

    if wlan.isconnected():
        print("Wi-Fi đã kết nối, IP ESP32:", wlan.ifconfig()[0])
        return True

    print("Kết nối Wi-Fi thất bại.")
    return False


def read_mhz19_co2():
    """Đọc nồng độ CO2 (ppm) từ cảm biến MH-Z19C qua UART."""
    if uart is None:
        return None
    while uart.any():
        uart.read()
    # Lệnh đọc khí CO2 chuẩn của MH-Z19
    cmd = bytearray([0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79])
    uart.write(cmd)
    time.sleep(0.1)

    resp = uart.read(9)
    if resp and len(resp) == 9 and resp[0] == 0xFF and resp[1] == 0x86:
        checksum = (0xFF - (sum(resp[1:8]) & 0xFF) + 1) & 0xFF
        if resp[8] == checksum:
            return float(resp[2] * 256 + resp[3])
    return None


def read_sensors(seq_id: int) -> dict:
    pir_val = 1 if pir.value() else 0

    if cfg.SIMULATE_SENSORS:
        global _sim_co2
        _sim_co2 = min(1800.0, _sim_co2 + (25.0 if pir_val else -10.0))
        co2_val = round(_sim_co2, 1)
        temp_c = 27.2
        humidity_pct = 63.0
    else:
        co2_read = read_mhz19_co2()
        co2_val = co2_read if co2_read is not None else 0.0
        temp_c = 27.0
        humidity_pct = 60.0

    # Định dạng timestamp ISO-8601 tương thích với backend/app.py
    t = time.gmtime()
    iso_ts = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}+00:00".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )

    return {
        "seq_id": seq_id,
        "timestamp": iso_ts,
        "co2_ppm": co2_val,
        "temp_c": temp_c,
        "humidity_pct": humidity_pct,
        "pir_active": pir_val,
    }


def post_telemetry(payload: dict):
    url = cfg.SERVER_URL.rstrip("/") + "/api/telemetry"
    res = None
    try:
        res = urequests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=ujson.dumps(payload),
        )
        print("POST telemetry status:", res.status_code, res.text)
    except Exception as e:
        print("Lỗi gửi telemetry:", e)
    finally:
        if res is not None:
            res.close()


def poll_command():
    global _last_applied_command_id
    url = cfg.SERVER_URL.rstrip("/") + "/api/command"
    res = None
    try:
        res = urequests.get(url)
        if res.status_code == 200:
            cmd = res.json()
            cmd_id = cmd.get("command_id")
            fan_on = bool(cmd.get("fan_on", False))
            if cmd_id and cmd_id != _last_applied_command_id:
                set_fan_state(fan_on)
                _last_applied_command_id = cmd_id
                print("Áp dụng lệnh mới:", cmd_id, "-> fan_on =", fan_on)
    except Exception as e:
        print("Lỗi lấy lệnh command:", e)
    finally:
        if res is not None:
            res.close()


def main():
    global _sim_seq
    set_fan_state(False)
    connect_wifi()

    last_telemetry_ts = 0
    last_poll_ts = 0

    while True:
        now = time.time()
        if not network.WLAN(network.STA_IF).isconnected():
            connect_wifi(timeout_sec=10)

        if now - last_poll_ts >= cfg.COMMAND_POLL_INTERVAL_SEC:
            poll_command()
            last_poll_ts = now

        if now - last_telemetry_ts >= cfg.TELEMETRY_INTERVAL_SEC:
            _sim_seq += 1
            sample = read_sensors(_sim_seq)
            post_telemetry(sample)
            last_telemetry_ts = now

        time.sleep(0.5)


if __name__ == "__main__":
    main()
