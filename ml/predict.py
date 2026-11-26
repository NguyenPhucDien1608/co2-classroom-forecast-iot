import os
import joblib
import numpy as np
import pandas as pd

from features import build_features, load_telemetry

MODEL_DIR = "ml/artifacts"


def predict_latest(
    db_path: str = "co2_system.db",
    threshold_ppm: float = 1000.0,
) -> dict:
    raw_df = load_telemetry(db_path)
    if raw_df.empty:
        return {
            "has_data": False,
            "co2_now": None,
            "pred_15m": None,
            "pred_30m": None,
            "fan_on": False,
            "reason": "Chưa có dữ liệu telemetry trong SQLite",
        }

    feat_df = build_features(raw_df)
    latest = feat_df.iloc[[-1]].copy()

    feature_cols = joblib.load(os.path.join(MODEL_DIR, "feature_cols.joblib"))
    model_15m = joblib.load(os.path.join(MODEL_DIR, "rf_co2_plus_15m.joblib"))
    model_30m = joblib.load(os.path.join(MODEL_DIR, "rf_co2_plus_30m.joblib"))

    X_live = latest[feature_cols].fillna(0.0)
    pred_15m = float(model_15m.predict(X_live)[0])
    pred_30m = float(model_30m.predict(X_live)[0])

    co2_now = float(latest["co2_ppm"].iloc[0])
    pir_active = int(latest["pir_active"].iloc[0])

    # Logic điều khiển thông gió chủ động
    if co2_now >= threshold_ppm:
        fan_on = True
        reason = f"CO2 hiện tại ({co2_now:.0f} ppm) >= ngưỡng {threshold_ppm:.0f} ppm"
    elif (pred_15m >= threshold_ppm or pred_30m >= threshold_ppm) and (
        pir_active == 1 or pred_15m > co2_now
    ):
        fan_on = True
        reason = (
            f"Dự báo vượt ngưỡng ({threshold_ppm:.0f} ppm): "
            f"+15m={pred_15m:.0f} ppm, +30m={pred_30m:.0f} ppm"
        )
    elif co2_now < threshold_ppm - 100.0 and pred_15m < threshold_ppm - 50.0:
        fan_on = False
        reason = f"CO2 đã hạ an toàn ({co2_now:.0f} ppm) và xu hướng giảm"
    else:
        fan_on = False
        reason = f"CO2 trong vùng an toàn ({co2_now:.0f} ppm), chưa cần bật quạt"

    return {
        "has_data": True,
        "timestamp": str(latest["timestamp"].iloc[0]),
        "co2_now": round(co2_now, 1),
        "pir_active": pir_active,
        "pred_15m": round(pred_15m, 1),
        "pred_30m": round(pred_30m, 1),
        "threshold_ppm": threshold_ppm,
        "fan_on": fan_on,
        "reason": reason,
    }


if __name__ == "__main__":
    result = predict_latest()
    for k, v in result.items():
        print(f"{k}: {v}")
