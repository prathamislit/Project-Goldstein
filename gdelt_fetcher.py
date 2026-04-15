"""
gdelt_fetcher.py — Pulls Goldstein Scale event data from GDELT via BigQuery.

Logic:
- Filters strictly by country codes for the active region (no geographic noise)
- Computes Volume-Weighted Average Goldstein Score per day
  (article volume = EventCode count per event; prevents minor anomalies from
   dominating over high-frequency major events)
- Outputs: data/gdelt_raw.csv
"""

import os
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
import config

def get_bq_client():
    """Authenticate BigQuery client from service account key or ADC."""
    creds_path = config.GOOGLE_APPLICATION_CREDENTIALS
    if creds_path and os.path.exists(creds_path):
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return bigquery.Client(project=config.GCP_PROJECT_ID, credentials=credentials)
    else:
        # Falls back to Application Default Credentials
        # Run: gcloud auth application-default login
        print("[gdelt_fetcher] No key file found — using Application Default Credentials.")
        return bigquery.Client(project=config.GCP_PROJECT_ID)


def build_query(region_cfg: dict, start_date: str, end_date: str) -> str:
    """
    Constructs the BigQuery SQL for the active region.

    Sqrt-Weighted Average (replaces linear NumArticles weighting):
      SUM(GoldsteinScale * SQRT(NumArticles)) / SUM(SQRT(NumArticles))

    Why sqrt and not raw NumArticles:
    - Linear weighting lets a single 500-article saturation event (e.g. a
      celebrity diplomatic row) dominate over a genuine escalation that only
      three wire services covered on a competing-news day.
    - sqrt dampens the dominance of high-volume days without ignoring salience
      entirely — a 400-article event still outweighs a 4-article event (10x
      weight), but not 100x as with linear weighting.
    - Reduces systematic bias from competing news cycles (weekends, US domestic
      stories crowding out regional geopolitical events).
    """
    country_list = ", ".join(f"'{c}'" for c in region_cfg["gdelt_countries"])

    # Convert YYYY-MM-DD to YYYYMMDD integer for GDELT's date format
    start_int = start_date.replace("-", "")
    end_int   = end_date.replace("-", "")

    query = f"""
    SELECT
        SQLDATE,
        SUM(GoldsteinScale * SQRT(NumArticles)) / NULLIF(SUM(SQRT(NumArticles)), 0) AS goldstein_wavg,
        SUM(NumArticles)                                                              AS total_articles,
        COUNT(*)                                                                      AS event_count,
        COUNT(DISTINCT {config.GDELT_COUNTRY_COL})                                   AS source_country_diversity
    FROM
        `{config.GDELT_TABLE}`
    WHERE
        {config.GDELT_DATE_COL} BETWEEN {start_int} AND {end_int}
        AND {config.GDELT_COUNTRY_COL} IN ({country_list})
        AND GoldsteinScale IS NOT NULL
        AND NumArticles > 0
    GROUP BY
        SQLDATE
    ORDER BY
        SQLDATE ASC
    """
    return query


def fetch_gdelt(save: bool = True) -> pd.DataFrame:
    """
    Main entry point. Pulls GDELT data, cleans dates, returns DataFrame.

    Known bug from v1 (fixed here):
    - GDELT dates are integers (20220103). Forcing format='%Y%m%d'
      prevents pandas from misinterpreting them as nanoseconds since epoch.
    """
    region_cfg = config.get_region_config()
    print(f"[gdelt_fetcher] Region: {config.ACTIVE_REGION} | {region_cfg['label']}")
    print(f"[gdelt_fetcher] Date range: {config.START_DATE} → {config.END_DATE}")
    print(f"[gdelt_fetcher] Countries: {region_cfg['gdelt_countries']}")

    client = get_bq_client()
    query  = build_query(region_cfg, config.START_DATE, config.END_DATE)

    print("[gdelt_fetcher] Running BigQuery job...")
    df = client.query(query).to_dataframe()
    print(f"[gdelt_fetcher] Rows returned: {len(df)}")

    if df.empty:
        raise ValueError("[gdelt_fetcher] No data returned. Check region config and date range.")

    # Fix the integer date bug from v1
    df["date"] = pd.to_datetime(df["SQLDATE"].astype(str), format="%Y%m%d")
    df = df.drop(columns=["SQLDATE"])
    df = df.sort_values("date").reset_index(drop=True)

    # Sanity check: flag days with very low article volume (potential noise)
    low_volume_days = df[df["total_articles"] < 5]
    if len(low_volume_days) > 0:
        print(f"[gdelt_fetcher] WARNING: {len(low_volume_days)} days with <5 articles — "
              f"Goldstein scores may be noisy on these dates.")

    # FLAW 10 fix: Validate source country diversity — detects FIPS filter failures.
    # If a key FIPS code is misconfigured, events drop to zero silently.
    # source_country_diversity < expected means a country is returning no events.
    n_countries = len(region_cfg["gdelt_countries"])
    expected_min_diversity = max(1, n_countries // 2)
    low_diversity = df[df["source_country_diversity"] < expected_min_diversity]
    if len(low_diversity) > 0:
        print(f"[gdelt_fetcher] WARNING: {len(low_diversity)} days with <{expected_min_diversity} "
              f"source countries — possible FIPS filter failure or genuine regional silence.")
    else:
        print(f"[gdelt_fetcher] FIPS validation: OK — all days have ≥{expected_min_diversity} "
              f"source countries (of {n_countries} configured).")

    if save:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        df.to_csv(config.GDELT_RAW_FILE, index=False)
        print(f"[gdelt_fetcher] Saved → {config.GDELT_RAW_FILE}")

    return df


if __name__ == "__main__":
    df = fetch_gdelt()
    print(df.head(10))
    print(f"\nGoldstein score range: {df['goldstein_wavg'].min():.2f} to {df['goldstein_wavg'].max():.2f}")
    print(f"Date range in data: {df['date'].min().date()} to {df['date'].max().date()}")
