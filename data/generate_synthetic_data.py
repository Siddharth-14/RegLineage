"""Generates fully synthetic customer/account/transaction/reg-report data.

Everything here is fabricated with a fixed seed (42) for one purpose: giving
lineage/scoring.py real data quality defects to find. Nothing in this file
reads from, or resembles data from, any real institution.

Defect rates are set noticeably above the ~2-6% figures a real bank's data
might show, so that the scorecard has something to flag on a fresh run
without depending on random luck. See README.md for the reasoning.
"""

import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

SEED = 42

# Fixed "as of" anchor so every generated run produces identical dates,
# independent of the wall-clock date the script happens to run on.
AS_OF_DATE = date(2025, 6, 30)

N_CUSTOMERS = 500
N_ACCOUNTS = 800
N_TRANSACTIONS = 5000

# Deliberately-elevated defect rates (see module docstring).
ACCOUNT_ORPHAN_RATE = 0.12          # accounts.customer_id left null
TXN_STALE_RATE = 0.12               # transactions backdated vs. their account
CUSTOMER_MISSING_KYC_RATE = 0.12    # customers.kyc_status left null
REPORT_MISMATCH_RATE = 0.12         # reg_report_extract.reported_value off

STALENESS_MIN_DAYS = 45
STALENESS_MAX_DAYS = 150

ACCOUNT_TYPES = ["checking", "savings", "credit_card", "loan"]
ACCOUNT_STATUSES = ["active", "active", "active", "closed", "frozen"]
KYC_STATUSES = ["verified", "verified", "pending", "rejected"]
CHANNELS = ["branch", "online", "atm", "wire", "mobile"]
CURRENCIES = ["USD", "USD", "USD", "USD", "EUR", "GBP"]

DATA_DIR = Path(__file__).resolve().parent


def _seed_everything():
    random.seed(SEED)
    np.random.seed(SEED)
    Faker.seed(SEED)


def _random_date(start: date, end: date, faker: Faker) -> date:
    return faker.date_between(start_date=start, end_date=end)


def generate_customers(faker: Faker) -> pd.DataFrame:
    rows = []
    for i in range(1, N_CUSTOMERS + 1):
        rows.append(
            {
                "customer_id": f"CUST{i:05d}",
                "name": faker.name(),
                "address": faker.address().replace("\n", ", "),
                "opened_date": _random_date(date(2015, 1, 1), AS_OF_DATE, faker),
                "kyc_status": random.choice(KYC_STATUSES),
            }
        )
    df = pd.DataFrame(rows)

    n_missing = int(round(N_CUSTOMERS * CUSTOMER_MISSING_KYC_RATE))
    missing_idx = np.random.choice(df.index, size=n_missing, replace=False)
    df.loc[missing_idx, "kyc_status"] = np.nan
    return df


def generate_accounts(faker: Faker, customer_ids: list) -> pd.DataFrame:
    rows = []
    for i in range(1, N_ACCOUNTS + 1):
        rows.append(
            {
                "account_id": f"ACCT{i:05d}",
                "customer_id": random.choice(customer_ids),
                "account_type": random.choice(ACCOUNT_TYPES),
                "opened_date": _random_date(date(2016, 1, 1), AS_OF_DATE, faker),
                "status": random.choice(ACCOUNT_STATUSES),
            }
        )
    df = pd.DataFrame(rows)

    n_orphan = int(round(N_ACCOUNTS * ACCOUNT_ORPHAN_RATE))
    orphan_idx = np.random.choice(df.index, size=n_orphan, replace=False)
    df.loc[orphan_idx, "customer_id"] = np.nan
    return df


def generate_transactions(faker: Faker, account_ids: list) -> pd.DataFrame:
    # Kept narrower than STALENESS_MIN_DAYS so the non-backdated "fresh"
    # population never crosses the freshness threshold by chance -- only
    # the deliberately backdated rows below should trigger it.
    recent_start = AS_OF_DATE - timedelta(days=25)
    account_choices = np.random.choice(account_ids, size=N_TRANSACTIONS, replace=True)

    rows = []
    for i in range(1, N_TRANSACTIONS + 1):
        rows.append(
            {
                "txn_id": f"TXN{i:06d}",
                "account_id": account_choices[i - 1],
                "amount": round(float(np.random.uniform(-2500, 5000)), 2),
                "currency": random.choice(CURRENCIES),
                "txn_date": _random_date(recent_start, AS_OF_DATE, faker),
                "channel": random.choice(CHANNELS),
            }
        )
    df = pd.DataFrame(rows)
    df["txn_date"] = pd.to_datetime(df["txn_date"])

    # Pick a pool of rows we're allowed to backdate: never more than half of
    # any single account's rows, so that account still has a "fresh" max
    # date for the freshness check to compare against.
    eligible_idx = []
    for account_id, group in df.groupby("account_id"):
        if len(group) < 3:
            continue
        cap = len(group) // 2
        eligible_idx.extend(
            np.random.choice(group.index, size=cap, replace=False).tolist()
        )

    n_stale_target = int(round(N_TRANSACTIONS * TXN_STALE_RATE))
    n_stale = min(n_stale_target, len(eligible_idx))
    stale_idx = np.random.choice(eligible_idx, size=n_stale, replace=False)

    backdate_days = np.random.randint(STALENESS_MIN_DAYS, STALENESS_MAX_DAYS + 1, size=n_stale)
    df.loc[stale_idx, "txn_date"] = df.loc[stale_idx, "txn_date"] - pd.to_timedelta(
        backdate_days, unit="D"
    )

    df["txn_date"] = df["txn_date"].dt.strftime("%Y-%m-%d")
    return df


def generate_reg_report_extract(accounts_df: pd.DataFrame, transactions_df: pd.DataFrame) -> pd.DataFrame:
    rollup = transactions_df.groupby("account_id")["amount"].sum()

    account_ids = accounts_df["account_id"].tolist()
    n_mismatch = int(round(len(account_ids) * REPORT_MISMATCH_RATE))
    mismatch_ids = set(np.random.choice(account_ids, size=n_mismatch, replace=False))

    rows = []
    for account_id in account_ids:
        true_value = float(rollup.get(account_id, 0.0))
        sign = random.choice([-1, 1])

        if account_id in mismatch_ids:
            if abs(true_value) > 100:
                deviation = true_value * np.random.uniform(0.15, 0.40)
            else:
                deviation = np.random.uniform(500, 2000)
            reported_value = true_value + sign * deviation
        else:
            if abs(true_value) > 100:
                noise = true_value * np.random.uniform(-0.005, 0.005)
            else:
                noise = np.random.uniform(-5, 5)
            reported_value = true_value + noise

        rows.append(
            {
                "report_field": "total_exposure",
                "source_account_id": account_id,
                "reported_value": round(reported_value, 2),
                "as_of_date": AS_OF_DATE.isoformat(),
            }
        )

    return pd.DataFrame(rows)


def generate(output_dir: Path = DATA_DIR) -> None:
    """Generates all four synthetic CSVs into output_dir."""
    _seed_everything()
    faker = Faker()
    Faker.seed(SEED)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    customers_df = generate_customers(faker)
    accounts_df = generate_accounts(faker, customers_df["customer_id"].tolist())
    transactions_df = generate_transactions(faker, accounts_df["account_id"].tolist())
    reg_report_df = generate_reg_report_extract(accounts_df, transactions_df)

    customers_df.to_csv(output_dir / "customers.csv", index=False)
    accounts_df.to_csv(output_dir / "accounts.csv", index=False)
    transactions_df.to_csv(output_dir / "transactions.csv", index=False)
    reg_report_df.to_csv(output_dir / "reg_report_extract.csv", index=False)


def data_exists(output_dir: Path = DATA_DIR) -> bool:
    output_dir = Path(output_dir)
    required = ["customers.csv", "accounts.csv", "transactions.csv", "reg_report_extract.csv"]
    return all((output_dir / name).exists() for name in required)


if __name__ == "__main__":
    generate()
    print(f"Synthetic data written to {DATA_DIR}")
