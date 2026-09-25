"""Network-free tests for burst-list parsing, archive listing, and obs-time parsing."""
from datetime import datetime, timezone

from app.collectors.collect_burst_list import parse_burst_list
from app.collectors.collect_ecallisto import _FILE_RE, file_covering, FitsFile
from app.processing.dynamic_spectrum import parse_obs_start

_SAMPLE = """Product: e-CALLISTO_2026_06.txt
# header comment
#Date 		Time		Type	Stations
20260615	05:17-05:21	IIIGG/3	HUMAIN, INDIA-OOTY, SRI-Lanka, TAIWAN-NCU
20260615	06:25-06:27	III/2	BIR, HUMAIN, MRO
20260601	00:00-00:00	---	##:##
20260601	##:##-##:##	---	"""


def test_parse_burst_list():
    events = parse_burst_list(_SAMPLE)
    # 3 valid time-ranged rows (the ##:## marker row is skipped).
    assert len(events) == 3
    first = events[0]
    assert first.date.isoformat() == "2026-06-15"
    assert first.start.strftime("%H:%M") == "05:17"
    assert "SRI-Lanka" in first.stations
    assert first.type == "IIIGG/3"


def test_archive_filename_regex():
    html = '<a href="SRI-Lanka_20260615_050431_59.fit.gz">x</a>'
    m = _FILE_RE.findall(html)
    assert m
    fname, station, ymd, hms, focus = m[0]
    assert station == "SRI-Lanka"
    assert ymd == "20260615"
    assert hms == "050431"
    assert focus == "59"


def test_file_covering_picks_window():
    base = "https://x/"
    files = [
        FitsFile("SRI-Lanka", datetime(2026, 6, 15, 5, 4, 31, tzinfo=timezone.utc), "a", base + "a"),
        FitsFile("SRI-Lanka", datetime(2026, 6, 15, 5, 19, 31, tzinfo=timezone.utc), "b", base + "b"),
        FitsFile("SRI-Lanka", datetime(2026, 6, 15, 5, 34, 31, tzinfo=timezone.utc), "c", base + "c"),
    ]
    # A burst at 05:21 falls inside the 05:19:31 window.
    target = datetime(2026, 6, 15, 5, 21, 0, tzinfo=timezone.utc)
    chosen = file_covering(files, "SRI-Lanka", target)
    assert chosen.filename == "b"


def test_parse_obs_start_ecallisto_format():
    header = {"DATE-OBS": "2026/06/15", "TIME-OBS": "05:04:31.725"}
    dt = parse_obs_start(header)
    assert dt == datetime(2026, 6, 15, 5, 4, 31, 725000, tzinfo=timezone.utc)


def test_parse_obs_start_iso_format():
    header = {"DATE-OBS": "2024-01-15T10:00:00"}
    dt = parse_obs_start(header)
    assert dt.year == 2024 and dt.hour == 10 and dt.tzinfo is not None
