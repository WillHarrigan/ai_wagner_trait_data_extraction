import asyncio
import math

import pandas as pd
import xlwings as xw


def export_validation_to_excel(validation_df, filepath, sheet_name="Validation"):
    """
    Write validation_df to Excel and color all 3 rows of each column triplet
    by the coded row value.

    Colors:
      Green  (code=1) — correct
      Red    (code=0) — incorrect
      Yellow (code=2) — needs manual review

    Args:
        validation_df:  Output of build_validation_df (3 rows per species_key)
        filepath:       Path to save the .xlsx file
        sheet_name:     Sheet name (default "Validation")
    """
    COLOR_MAP = {
        0: (255, 102, 102),
        1: (102, 204, 102),
        2: (255, 255, 102),
    }

    skip_cols = {
        "row_type", "wagner_pg_number", "average_chromosome_number"
    }

    col_indices = {col: i + 1 for i, col in enumerate(validation_df.columns)}

    app = xw.App(visible=False)
    try:
        wb = app.books.add()
        ws = wb.sheets[0]
        ws.name = sheet_name

        ws.range("A1").value = [validation_df.columns.tolist()] + validation_df.values.tolist()

        n_rows = len(validation_df)
        assert n_rows % 3 == 0, "validation_df must have 3 rows per species_key"

        for triplet_start in range(0, n_rows, 3):
            coded_row = validation_df.iloc[triplet_start + 2]
            xl_row1 = triplet_start + 2
            xl_row3 = triplet_start + 4

            for col in validation_df.columns:
                if col in skip_cols:
                    continue
                try:
                    code = int(coded_row[col])
                except (TypeError, ValueError):
                    continue
                if code not in COLOR_MAP:
                    continue

                ws.range(
                    (xl_row1, col_indices[col]),
                    (xl_row3, col_indices[col])
                ).color = COLOR_MAP[code]

        wb.save(filepath)
        wb.close()
        print(f"Saved: {filepath}")
    finally:
        app.quit()
