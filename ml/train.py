import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

from features import build_features, load_telemetry

MODEL_DIR = "ml/artifacts"
FEATURE_COLS = [
    "co2_ppm",
    "temp_c",
    "humidity_pct",
    "pir_active",
    "delta_co2_5m",
    "slope_ppm_per_min_5m",
    "delta_co2_15m",
    "slope_ppm_per_min_15m",
]


def make_synthetic_training_data(n_minutes: int = 180) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=n_minutes)
    times = pd.date_range(start=start, periods=n_minutes, freq="1min")

    co2 = 550.0
    rows = []
    for idx, dt in enumerate(times):
        pir = 1 if 20 <= idx <= 110 else (1 if 111 <= idx <= 130 and idx % 2 == 0 else 0)
        if 20 <= idx <= 110:
            drift = rng.uniform(6.0, 14.0)
        elif idx > 110:
            drift = rng.uniform(-12.0, -4.0)
        else:
            drift = rng.uniform(-1.5, 2.0)

        co2 = float(np.clip(co2 + drift + rng.normal(0, 3.0), 420.0, 2200.0))
        rows.append(
            {
                "id": idx + 1,
                "seq_id": idx + 1,
                "timestamp": dt.isoformat(),
                "co2_ppm": round(co2, 1),
                "temp_c": round(26.5 + rng.normal(0, 0.4), 1),
                "humidity_pct": round(62.0 + rng.normal(0, 2.0), 1),
                "pir_active": pir,
                "received_at": dt.timestamp(),
            }
        )
    return pd.DataFrame(rows)


def train_and_evaluate():
    os.makedirs(MODEL_DIR, exist_ok=True)

    raw_df = load_telemetry()
    feat_df = build_features(raw_df) if not raw_df.empty else pd.DataFrame()

    usable_real = (
        feat_df.dropna(subset=FEATURE_COLS + ["co2_t_plus_15m", "co2_t_plus_30m"])
        if not feat_df.empty
        else pd.DataFrame()
    )

    if len(usable_real) >= 30:
        print(f"Huấn luyện bằng dữ liệu thực từ SQLite ({len(usable_real)} mẫu hợp lệ).")
        train_df = usable_real
    else:
        print(
            f"Dữ liệu SQLite hiện có {len(usable_real)} mẫu đủ nhãn (< 30). "
            "Dùng dữ liệu phòng học giả lập 180 phút để huấn luyện thử nghiệm."
        )
        sim_raw = make_synthetic_training_data(180)
        sim_feat = build_features(sim_raw)
        train_df = sim_feat.dropna(subset=FEATURE_COLS + ["co2_t_plus_15m", "co2_t_plus_30m"]).copy()

    split_idx = int(len(train_df) * 0.8)
    tr = train_df.iloc[:split_idx]
    te = train_df.iloc[split_idx:]

    X_tr, X_te = tr[FEATURE_COLS].fillna(0.0), te[FEATURE_COLS].fillna(0.0)

    for h in (15, 30):
        target_col = f"co2_t_plus_{h}m"
        y_tr, y_te = tr[target_col], te[target_col]

        model = RandomForestRegressor(n_estimators=120, random_state=42)
        model.fit(X_tr, y_tr)
        preds = model.predict(X_te)

        mae_ml = mean_absolute_error(y_te, preds)
        mae_pers = mean_absolute_error(y_te, te[f"baseline_persistence_{h}m"])
        mae_lin = mean_absolute_error(y_te, te[f"baseline_linear_{h}m"])

        print(
            f"[Mốc +{h} phút] MAE Mô hình: {mae_ml:.2f} ppm | "
            f"Persistence: {mae_pers:.2f} | Linear: {mae_lin:.2f}"
        )
        joblib.dump(model, os.path.join(MODEL_DIR, f"rf_co2_plus_{h}m.joblib"))

    joblib.dump(FEATURE_COLS, os.path.join(MODEL_DIR, "feature_cols.joblib"))
    print(f"Đã lưu mô hình vào thư mục: {MODEL_DIR}")


if __name__ == "__main__":
    train_and_evaluate()
