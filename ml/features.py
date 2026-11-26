import sqlite3
import pandas as pd


def _ensure_dt(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "dt" not in out.columns and "timestamp" in out.columns:
        out["dt"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    elif "dt" in out.columns:
        out["dt"] = pd.to_datetime(out["dt"], utc=True, errors="coerce")
    return out.dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)


def load_telemetry(db_path: str = "co2_system.db") -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT id, seq_id, timestamp, co2_ppm, temp_c, humidity_pct, pir_active, received_at
        FROM telemetry
        """,
        conn,
    )
    conn.close()

    if df.empty:
        return df

    return _ensure_dt(df)


def attach_future_targets(
    df: pd.DataFrame,
    horizons_min: tuple[int, ...] = (15, 30),
    tolerance_sec: int = 30,
) -> pd.DataFrame:
    if df.empty:
        return df

    out = _ensure_dt(df)
    future_lookup = out[["dt", "co2_ppm"]].sort_values("dt")
    tol = pd.Timedelta(seconds=tolerance_sec)

    for h in horizons_min:
        probe = pd.DataFrame(
            {
                "target_dt": out["dt"] + pd.Timedelta(minutes=h),
                "orig_idx": out.index,
            }
        ).sort_values("target_dt")

        merged = pd.merge_asof(
            probe,
            future_lookup,
            left_on="target_dt",
            right_on="dt",
            direction="nearest",
            tolerance=tol,
        ).sort_values("orig_idx")

        out[f"co2_t_plus_{h}m"] = merged["co2_ppm"].to_numpy()
        out[f"baseline_persistence_{h}m"] = out["co2_ppm"].to_numpy()

    return out


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    feat = attach_future_targets(df)
    dt_indexed = feat.set_index("dt")

    for win_min in (5, 15):
        win = f"{win_min}min"
        shifted_min = dt_indexed["co2_ppm"].shift(1).rolling(win, min_periods=1).min()
        delta_co2 = feat["co2_ppm"] - shifted_min.to_numpy()
        feat[f"delta_co2_{win_min}m"] = delta_co2
        feat[f"slope_ppm_per_min_{win_min}m"] = delta_co2 / float(win_min)

    slope_15 = feat["slope_ppm_per_min_15m"].fillna(0.0)
    for h in (15, 30):
        feat[f"baseline_linear_{h}m"] = feat["co2_ppm"] + slope_15 * float(h)

    return feat


if __name__ == "__main__":
    raw_df = load_telemetry()
    print(f"Số dòng dữ liệu đọc được từ SQLite: {len(raw_df)}")
    if not raw_df.empty:
        dataset = build_features(raw_df)
        cols = [
            "seq_id",
            "co2_ppm",
            "slope_ppm_per_min_15m",
            "baseline_persistence_15m",
            "baseline_linear_15m",
            "co2_t_plus_15m",
        ]
        print(dataset[cols].tail(10))
