"""
tests/test_data_fetcher.py
──────────────────────────
Offline unit tests for src/data_fetcher.py.
All HTTP calls are mocked — CBSL does not need to be reachable.
"""

import os
import pytest
from datetime import date
from unittest.mock import MagicMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_PDF = b"%PDF-1.4 fake pdf content"
INVALID_BODY = b"<html>not a pdf</html>"
REQUESTS_GET = "src.data_fetcher.requests.get"
ENSURE = "src.data_fetcher.ensure_dir"


def _mock_resp(status_code: int, content: bytes = VALID_PDF) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = content.decode("latin-1", errors="replace")
    resp.raise_for_status = MagicMock(
        side_effect=None if status_code < 400 else Exception(f"HTTP {status_code}")
    )
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# 1. URL generation
# ═══════════════════════════════════════════════════════════════════════════════

def test_date_to_url_format():
    from src.data_fetcher import _date_to_url
    url = _date_to_url(date(2026, 11, 23))
    assert "price_report_20261123_e.pdf" in url
    assert url.startswith("https://")


def test_date_to_url_zero_padded():
    from src.data_fetcher import _date_to_url
    assert "20260105" in _date_to_url(date(2026, 1, 5))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PDF validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_valid_pdf_magic():
    from src.data_fetcher import _is_valid_pdf
    assert _is_valid_pdf(b"%PDF-1.4 content") is True


def test_invalid_pdf_rejected():
    from src.data_fetcher import _is_valid_pdf
    assert _is_valid_pdf(b"<html>garbage</html>") is False


def test_empty_content_rejected():
    from src.data_fetcher import _is_valid_pdf
    assert _is_valid_pdf(b"") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _try_date_url — per-date fetch logic
# ═══════════════════════════════════════════════════════════════════════════════

@patch(ENSURE)
@patch(REQUESTS_GET)
def test_try_date_url_success(mock_get, mock_ensure, tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_fetcher.PDF_DIR", str(tmp_path))
    mock_get.return_value = _mock_resp(200, VALID_PDF)

    from src.data_fetcher import _try_date_url
    result = _try_date_url(date(2026, 11, 20))

    assert result is not None
    assert result.endswith("price_report_20261120.pdf")
    assert os.path.exists(result)


@patch(REQUESTS_GET)
def test_try_date_url_404_returns_none(mock_get):
    mock_get.return_value = _mock_resp(404)

    from src.data_fetcher import _try_date_url
    assert _try_date_url(date(2026, 11, 20)) is None


@patch(REQUESTS_GET)
def test_try_date_url_403_raises_permission_error(mock_get):
    mock_get.return_value = _mock_resp(403)

    from src.data_fetcher import _try_date_url
    with pytest.raises(PermissionError, match="403"):
        _try_date_url(date(2026, 11, 20))


@patch(REQUESTS_GET)
def test_try_date_url_429_raises_runtime_error(mock_get):
    mock_get.return_value = _mock_resp(429)

    from src.data_fetcher import _try_date_url
    with pytest.raises(RuntimeError, match="429"):
        _try_date_url(date(2026, 11, 20))


@patch(REQUESTS_GET)
def test_try_date_url_500_raises_runtime_error(mock_get):
    mock_get.return_value = _mock_resp(500)

    from src.data_fetcher import _try_date_url
    with pytest.raises(RuntimeError, match="500"):
        _try_date_url(date(2026, 11, 20))


@patch(ENSURE)
@patch(REQUESTS_GET)
def test_try_date_url_invalid_pdf_content_returns_none(mock_get, mock_ensure, tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_fetcher.PDF_DIR", str(tmp_path))
    mock_get.return_value = _mock_resp(200, INVALID_BODY)

    from src.data_fetcher import _try_date_url
    assert _try_date_url(date(2026, 11, 20)) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Local cache reuse
# ═══════════════════════════════════════════════════════════════════════════════

def test_existing_valid_pdf_reused(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_fetcher.PDF_DIR", str(tmp_path))
    pdf_path = tmp_path / "price_report_20261120.pdf"
    pdf_path.write_bytes(VALID_PDF)

    with patch(REQUESTS_GET) as mock_get:
        from src.data_fetcher import _try_date_url
        result = _try_date_url(date(2026, 11, 20))
        mock_get.assert_not_called()

    assert result == str(pdf_path)


def test_corrupt_local_pdf_re_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_fetcher.PDF_DIR", str(tmp_path))
    pdf_path = tmp_path / "price_report_20261120.pdf"
    pdf_path.write_bytes(b"corrupt garbage")  # bad magic

    with patch(REQUESTS_GET, return_value=_mock_resp(200, VALID_PDF)):
        from src.data_fetcher import _try_date_url
        result = _try_date_url(date(2026, 11, 20))

    assert result is not None
    with open(result, "rb") as f:
        assert f.read(5) == b"%PDF-"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. _fetch_by_date — lookback loop
# ═══════════════════════════════════════════════════════════════════════════════

@patch("src.data_fetcher._try_date_url")
def test_fetch_by_date_skips_404_days(mock_try):
    # First 2 days → None (404), 3rd → success
    mock_try.side_effect = [None, None, "/data/raw_pdfs/price_report_20261120.pdf"]

    from src.data_fetcher import _fetch_by_date
    result = _fetch_by_date(max_lookback=5)

    assert result == "/data/raw_pdfs/price_report_20261120.pdf"
    assert mock_try.call_count == 3


@patch("src.data_fetcher._try_date_url")
def test_fetch_by_date_raises_when_lookback_exhausted(mock_try):
    mock_try.return_value = None  # all 404

    from src.data_fetcher import _fetch_by_date
    with pytest.raises(FileNotFoundError, match="no PDF found"):
        _fetch_by_date(max_lookback=3)


@patch("src.data_fetcher._try_date_url")
def test_fetch_by_date_propagates_403_immediately(mock_try):
    mock_try.side_effect = PermissionError("HTTP 403")

    from src.data_fetcher import _fetch_by_date
    with pytest.raises(PermissionError):
        _fetch_by_date(max_lookback=5)

    assert mock_try.call_count == 1  # must NOT continue after 403


@patch("src.data_fetcher._try_date_url")
def test_fetch_by_date_propagates_429_immediately(mock_try):
    mock_try.side_effect = RuntimeError("HTTP 429")

    from src.data_fetcher import _fetch_by_date
    with pytest.raises(RuntimeError, match="429"):
        _fetch_by_date(max_lookback=5)

    assert mock_try.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. HTML fallback strategy
# ═══════════════════════════════════════════════════════════════════════════════

HTML_WITH_PDF_LINK = b"""
<html><body>
  <a href="/sites/default/files/cbslweb_documents/statistics/pricerpt/price_report_20261120_e.pdf">
    Daily Price Report
  </a>
</body></html>
"""


@patch(ENSURE)
@patch(REQUESTS_GET)
def test_html_fallback_discovers_and_downloads_pdf(mock_get, mock_ensure, tmp_path, monkeypatch):
    monkeypatch.setattr("src.data_fetcher.PDF_DIR", str(tmp_path))

    listing_resp = _mock_resp(200, HTML_WITH_PDF_LINK)
    listing_resp.text = HTML_WITH_PDF_LINK.decode()
    pdf_resp = _mock_resp(200, VALID_PDF)
    mock_get.side_effect = [listing_resp, pdf_resp]

    from src.data_fetcher import _fetch_by_html
    result = _fetch_by_html()

    assert "price_report_20261120" in result
    assert os.path.exists(result)


@patch(REQUESTS_GET)
def test_html_fallback_raises_when_no_links(mock_get):
    empty_html = b"<html><body>no links here</body></html>"
    resp = _mock_resp(200, empty_html)
    resp.text = empty_html.decode()
    mock_get.return_value = resp

    from src.data_fetcher import _fetch_by_html
    with pytest.raises(Exception, match="no PDF link found"):
        _fetch_by_html()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. fetch_today_pdf — primary then fallback
# ═══════════════════════════════════════════════════════════════════════════════

@patch("src.data_fetcher._fetch_by_date")
def test_fetch_today_pdf_uses_date_strategy_first(mock_date):
    mock_date.return_value = "/data/raw_pdfs/price_report_20261120.pdf"

    from src.data_fetcher import fetch_today_pdf
    with patch(ENSURE):
        result = fetch_today_pdf()

    mock_date.assert_called_once()
    assert "20261120" in result


@patch("src.data_fetcher._fetch_by_html")
@patch("src.data_fetcher._fetch_by_date")
def test_fetch_today_pdf_falls_back_to_html_on_file_not_found(mock_date, mock_html):
    mock_date.side_effect = FileNotFoundError("no PDF in lookback")
    mock_html.return_value = "/data/raw_pdfs/price_report_20261118.pdf"

    from src.data_fetcher import fetch_today_pdf
    with patch(ENSURE):
        result = fetch_today_pdf()

    mock_html.assert_called_once()
    assert "20261118" in result


@patch("src.data_fetcher._fetch_by_html")
@patch("src.data_fetcher._fetch_by_date")
def test_fetch_today_pdf_does_not_fall_back_on_403(mock_date, mock_html):
    mock_date.side_effect = PermissionError("HTTP 403")

    from src.data_fetcher import fetch_today_pdf
    with patch(ENSURE):
        with pytest.raises(PermissionError):
            fetch_today_pdf()

    mock_html.assert_not_called()


@patch("src.data_fetcher._fetch_by_html")
@patch("src.data_fetcher._fetch_by_date")
def test_fetch_today_pdf_raises_when_both_fail(mock_date, mock_html):
    mock_date.side_effect = FileNotFoundError("exhausted")
    mock_html.side_effect = Exception("listing page down")

    from src.data_fetcher import fetch_today_pdf
    with patch(ENSURE):
        with pytest.raises(RuntimeError, match="Both PDF discovery strategies failed"):
            fetch_today_pdf()
