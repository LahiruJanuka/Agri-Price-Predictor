"""
tests/test_pdf_parser_dates.py
───────────────────────────────
Offline unit tests for date extraction in src/pdf_parser.py and
price-date association in src/data_cleaner.py.

No live CBSL requests. PDF extraction is mocked with realistic DataFrames.
"""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


def _make_raw_df(label_row, date_row, extra_rows=None):
    """
    Build a minimal camelot-style raw DataFrame that mimics the CBSL PDF layout.
    
    row 0 : label row  (e.g. "Last Friday", "Yesterday", ...)
    row 1 : "Today" labels
    row 2 : date strings for the previous column (e.g. "20.11.2026")
    row 3+ : commodity data
    """
    rows = [label_row, ["", "", "Today", "", "Today", "", "Today", "", "Today", "", "Today", "Today"], date_row]
    if extra_rows:
        rows.extend(extra_rows)
    df = pd.DataFrame(rows, columns=[f"col_{i}" for i in range(len(label_row))])
    return df


# 1. _parse_date_string
class TestParseDateString:
    def setup_method(self):
        from src.pdf_parser import _parse_date_string
        self.parse = _parse_date_string

    def test_dd_mm_yyyy_dot(self):
        result = self.parse("20.11.2026")
        assert result == datetime(2026, 11, 20)

    def test_yyyy_mm_dd(self):
        result = self.parse("2026-11-20")
        assert result == datetime(2026, 11, 20)

    def test_dd_slash_mm_slash_yyyy(self):
        result = self.parse("20/11/2026")
        assert result == datetime(2026, 11, 20)

    def test_empty_string_returns_none(self):
        assert self.parse("") is None

    def test_non_date_string_returns_none(self):
        assert self.parse("Yesterday") is None
        assert self.parse("Last Friday") is None
        assert self.parse("n.a.") is None

    def test_embedded_in_whitespace(self):
        result = self.parse("  20.11.2026  ")
        assert result == datetime(2026, 11, 20)

    def test_invalid_date_values_returns_none(self):
        # day 99 is invalid
        assert self.parse("99.13.2026") is None


# 2. extract_report_dates — normal consecutive dates
class TestExtractReportDates:
    def setup_method(self):
        from src.pdf_parser import extract_report_dates
        self.extract = extract_report_dates

    def _df(self, prev_date_str):
        """Build minimal DataFrame with prev_date_str in row 2."""
        rows = [
            ["", "", "Yesterday", "", "Yesterday", "", "Yesterday", "", "Yesterday", "", "Yesterday", ""],
            ["", "", "Today",     "", "Today",     "", "Today",     "", "Today",     "", "Today",     "Today"],
            ["", "", prev_date_str, "", prev_date_str, "", prev_date_str, "", prev_date_str, "", prev_date_str, ""],
        ]
        return pd.DataFrame(rows, columns=[f"col_{i}" for i in range(12)])

    def _df_label(self, label, prev_date_str):
        """Build DataFrame with a custom label (e.g. 'Last Friday')."""
        rows = [
            ["", "", label, "", label, "", label, "", label, "", label, ""],
            ["", "", "Today", "", "Today", "", "Today", "", "Today", "", "Today", "Today"],
            ["", "", prev_date_str, "", prev_date_str, "", prev_date_str, "", prev_date_str, "", prev_date_str, ""],
        ]
        return pd.DataFrame(rows, columns=[f"col_{i}" for i in range(12)])

    def test_consecutive_dates(self):
        """Today=23.11.2026, Previous=22.11.2026 (normal weekday)."""
        df = self._df("22.11.2026")
        report, prev = self.extract(df, "2026-11-23")
        assert report == "2026-11-23"
        assert prev == "2026-11-22"

    def test_weekend_gap(self):
        """Today=Monday 23.11.2026, Previous=Friday 20.11.2026."""
        df = self._df("20.11.2026")
        report, prev = self.extract(df, "2026-11-23")
        assert report == "2026-11-23"
        assert prev == "2026-11-20"

    def test_public_holiday_gap(self):
        """Today=24.11.2026, Previous=20.11.2026 (4-day gap)."""
        df = self._df("20.11.2026")
        report, prev = self.extract(df, "2026-11-24")
        assert report == "2026-11-24"
        assert prev == "2026-11-20"

    def test_last_friday_label(self):
        """Label 'Last Friday' — only the date string matters, not the label."""
        df = self._df_label("Last Friday", "20.11.2026")
        report, prev = self.extract(df, "2026-11-23")
        assert prev == "2026-11-20"

    def test_missing_date_in_pdf_returns_none(self):
        """PDF header has no date strings — prev_date must be None."""
        rows = [
            ["", "", "Yesterday", "", "Yesterday"],
            ["", "", "Today", "", "Today"],
            ["", "", "", "", ""],         # no date strings
        ]
        df = pd.DataFrame(rows, columns=[f"col_{i}" for i in range(5)])
        report, prev = self.extract(df, "2026-11-23")
        assert report == "2026-11-23"
        assert prev is None

    def test_date_not_before_report_date_is_rejected(self):
        """A date >= report_date must be ignored."""
        df = self._df("25.11.2026")   # future date, later than report
        report, prev = self.extract(df, "2026-11-23")
        assert prev is None

    def test_irregular_spacing_in_cell(self):
        """Date with extra whitespace inside a cell."""
        rows = [
            ["", "", "Yesterday", "", "Yesterday"],
            ["", "", "Today",     "", "Today"],
            ["", "", "  20.11.2026  ", "", "  20.11.2026  "],
        ]
        df = pd.DataFrame(rows, columns=[f"col_{i}" for i in range(5)])
        report, prev = self.extract(df, "2026-11-23")
        assert prev == "2026-11-20"

    def test_multiple_date_candidates_picks_most_recent(self):
        """If multiple earlier dates appear, the most recent is used."""
        rows = [
            ["", "", "18.11.2026", "", "20.11.2026"],  # two different prior dates
            ["", "", "Today",      "", "Today"],
            ["", "", "",           "", ""],
        ]
        df = pd.DataFrame(rows, columns=[f"col_{i}" for i in range(5)])
        report, prev = self.extract(df, "2026-11-23")
        assert prev == "2026-11-20"   # most recent of the two


# 3. data_cleaner.clean_raw_data — prices associated with correct dates
def _make_cleaner_df(report_date: str, prev_date, item_rows: list[dict]) -> pd.DataFrame:
    """
    Build a minimal raw DataFrame as data_cleaner.clean_raw_data expects:
    columns col_0..col_11, report_date, prev_date.
    item_rows: list of dicts with keys: item, unit, today_price, prev_price.
    Category is implicitly VEGETABLES (uses default column matrix).
    """
    # Header row (category)
    header = {f"col_{i}": "" for i in range(12)}
    header["col_5"] = "VEGETABLES"
    header["report_date"] = report_date
    header["prev_date"] = prev_date

    rows = [header]
    for r in item_rows:
        row = {f"col_{i}": "" for i in range(12)}
        row["col_0"] = r["item"]
        row["col_1"] = "Rs./kg"
        # col_2 = prev Wholesale Pettah, col_3 = today Wholesale Pettah
        row["col_2"] = r["prev_price"]
        row["col_3"] = r["today_price"]
        row["report_date"] = report_date
        row["prev_date"] = prev_date
        rows.append(row)

    return pd.DataFrame(rows)


class TestCleanRawDataDates:
    def setup_method(self):
        from src.data_cleaner import clean_raw_data
        self.clean = clean_raw_data

    def test_today_prices_stored_under_report_date(self):
        df = _make_cleaner_df(
            "2026-11-23", "2026-11-20",
            [{"item": "Beans", "today_price": "400", "prev_price": "550"}]
        )
        result = self.clean(df)
        today_rows = result[(result["item"] == "Beans") & (result["market"] == "Pettah")
                            & (result["price_type"] == "Wholesale")]
        report_date_row = today_rows[today_rows["date"] == pd.Timestamp("2026-11-23")]
        assert len(report_date_row) == 1
        assert report_date_row.iloc[0]["price"] == 400.0

    def test_prev_prices_stored_under_prev_date_not_minus_one(self):
        """Weekend gap: prev_date is 20 Nov, NOT 22 Nov (report - 1)."""
        df = _make_cleaner_df(
            "2026-11-23", "2026-11-20",
            [{"item": "Beans", "today_price": "400", "prev_price": "550"}]
        )
        result = self.clean(df)
        pettah_ws = result[(result["item"] == "Beans") & (result["market"] == "Pettah")
                           & (result["price_type"] == "Wholesale")]
        prev_row = pettah_ws[pettah_ws["date"] == pd.Timestamp("2026-11-20")]
        assert len(prev_row) == 1
        assert prev_row.iloc[0]["price"] == 550.0
        # Must NOT be stored under 2026-11-22 (report_date - 1 day)
        wrong_row = pettah_ws[pettah_ws["date"] == pd.Timestamp("2026-11-22")]
        assert len(wrong_row) == 0

    def test_prev_prices_skipped_when_prev_date_missing(self):
        """If prev_date is None/NaN, previous-report column must be dropped."""
        df = _make_cleaner_df(
            "2026-11-23", None,
            [{"item": "Beans", "today_price": "400", "prev_price": "550"}]
        )
        result = self.clean(df)
        pettah_ws = result[(result["item"] == "Beans") & (result["market"] == "Pettah")
                           & (result["price_type"] == "Wholesale")]
        # Only today's row should be present
        assert len(pettah_ws) == 1
        assert pettah_ws.iloc[0]["date"] == pd.Timestamp("2026-11-23")

    def test_prices_not_stored_under_system_date_assumption(self):
        """
        Guard: even if the gap is 1 day, the actual prev_date must be used,
        not a hardcoded 'report_date - 1 day'.
        This catches a regression to the old timedelta(days=1) assumption.
        """
        # 4-day gap (Poya + weekend)
        df = _make_cleaner_df(
            "2026-11-24", "2026-11-20",
            [{"item": "Carrot", "today_price": "600", "prev_price": "700"}]
        )
        result = self.clean(df)
        pettah_ws = result[(result["item"] == "Carrot") & (result["market"] == "Pettah")
                           & (result["price_type"] == "Wholesale")]
        dates_stored = set(pettah_ws["date"].dt.strftime("%Y-%m-%d"))
        assert "2026-11-24" in dates_stored   # today
        assert "2026-11-20" in dates_stored   # actual PDF prev date
        assert "2026-11-23" not in dates_stored   # NOT report_date - 1
