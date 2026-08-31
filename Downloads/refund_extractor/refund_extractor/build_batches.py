"""
Usage:
    python3 build_batches.py draft_output.xlsx [output_folder] [--batch-size 25]

Run this AFTER you've opened draft_output.xlsx, checked the "Review" sheet,
and corrected any Transaction Amount / Remittance Information / other
cells on the "Data" sheet that needed a human eye.

Splits the "Data" sheet into files of `--batch-size` rows (default 25),
each written as its own .xlsx named after the sum of that batch's
Transaction Amount column (e.g. "125675.xlsx"). Instruction ID is
renumbered 1..N within each batch file.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

COLUMNS = [
    "Instruction ID", "Creditor Name", "Creditor Account Number",
    "Creditor Account Type", "Creditor Bank", "Creditor Bank Branch",
    "Debtor Name", "Debtor Account Number", "Debtor Account Type",
    "Transaction Amount", "Transaction Purpose", "Remittance Information",
    "Creditor National ID",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft_xlsx")
    ap.add_argument("output_folder", nargs="?", default=None)
    ap.add_argument("--batch-size", type=int, default=25)
    args = ap.parse_args()

    draft_path = Path(args.draft_xlsx)
    out_folder = Path(args.output_folder) if args.output_folder else draft_path.parent / "batches"
    out_folder.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(draft_path, sheet_name="Data", dtype=str)
    df = df[COLUMNS]  # enforce exact column set/order

    missing_amount = df["Transaction Amount"].isna() | (df["Transaction Amount"].astype(str).str.strip() == "")
    if missing_amount.any():
        print(f"WARNING: {missing_amount.sum()} row(s) have a blank Transaction Amount. "
              f"They'll be treated as 0 in the batch total — fix them in the draft first if that's not intended.")

    amounts = pd.to_numeric(df["Transaction Amount"], errors="coerce").fillna(0)

    n = len(df)
    batch_size = args.batch_size
    num_batches = (n + batch_size - 1) // batch_size
    used_names = set()

    for b in range(num_batches):
        start, end = b * batch_size, min((b + 1) * batch_size, n)
        chunk = df.iloc[start:end].copy()
        chunk["Instruction ID"] = range(1, len(chunk) + 1)
        total = amounts.iloc[start:end].sum()

        # Format the total for a filename: whole number if it is one, else keep decimals.
        if float(total).is_integer():
            total_str = str(int(total))
        else:
            total_str = f"{total:.2f}"

        filename = f"{total_str}.xlsx"
        candidate = filename
        suffix = 2
        while candidate in used_names:
            candidate = f"{total_str}_{suffix}.xlsx"
            suffix += 1
        used_names.add(candidate)

        out_path = out_folder / candidate
        chunk.to_excel(out_path, index=False, sheet_name="Data")
        print(f"Batch {b + 1}/{num_batches}: rows {start + 1}-{end} -> {out_path.name} (sum={total_str})")

    print(f"\nDone — {num_batches} file(s) written to {out_folder}")


if __name__ == "__main__":
    main()
