"""Tests for pipeline.bundle and pipeline.position_table — Plan1 T4/T6/T7.

Run: cd tools/amtrak-position-engine && python3 -m pytest pipeline/tests/test_bundle.py -v
"""
import json
import tempfile
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

PLAN0_TOP_FIELDS = {
    "leg", "schedule_basis", "stations", "geometry", "units", "layers",
    "position_table", "eta_table", "proxy",
}


def _make_fake_bundle_json(tmp_path, proxy=True):
    """Write a minimal but valid bundle.json for validate_bundle tests."""
    leg58_dir = tmp_path / "leg58"
    leg58_dir.mkdir()
    audio_dir = leg58_dir / "audio"
    audio_dir.mkdir()

    mp3_path = audio_dir / "abc123.mp3"
    mp3_path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00")

    bundle = {
        "leg": "58",
        "proxy": proxy,
        "schedule_basis": {
            "kind": "trip-actual",
            "valid_dates": ["2026-07-11"],
        },
        "stations": [
            {
                "code": "NOL",
                "name": "New Orleans, LA",
                "mile": 0.0,
                "lat": 29.946,
                "lon": -90.078,
                "sched_arr": None,
                "sched_dep": "2026-07-11T15:45:00-05:00",
                "dwell_min": 0,
            },
            {
                "code": "CHI",
                "name": "Chicago, IL",
                "mile": 934.0,
                "lat": 41.879,
                "lon": -87.639,
                "sched_arr": "2026-07-12T11:15:00-05:00",
                "sched_dep": None,
                "dwell_min": 0,
            },
        ],
        "geometry": {
            "type": "LineString",
            "coordinates": [[-90.078, 29.946], [-87.639, 41.879]],
        },
        "units": [
            {
                "id": "58-0",
                "kind": "squib",
                "mile": 0.0,
                "place": "New Orleans",
                "side": "ahead",
                "salience": 5,
                "theme": "test",
                "text": "Hello world.",
                "lat": 29.946,
                "lon": -90.078,
                "audio": "audio/abc123.mp3",
                "dur_s": 4.8,
            }
        ],
        "layers": {
            "guide": {},
            "lore": {},
            "science": {},
            "connections": {},
            "themes": {},
        },
        "position_table": [
            [0, 0.0, 29.946, -90.078],
            [10, 15.0, 30.1, -90.2],
            [20, 30.0, 30.3, -90.3],
        ],
        "eta_table": [
            {"station_code": "JAN", "p10_min": 210, "p50_min": 225, "p90_min": 250},
        ],
    }
    (leg58_dir / "bundle.json").write_text(json.dumps(bundle))
    return leg58_dir, bundle


# ── test_build_bundle ─────────────────────────────────────────────────────────

class TestBuildBundle:

    def test_emits_all_plan0_fields(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        missing = PLAN0_TOP_FIELDS - set(result.keys())
        assert not missing, f"Missing Plan-0 fields: {missing}"

    def test_proxy_flag_is_true_in_proxy_mode(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        assert result["proxy"] is True

    def test_leg_field_is_string(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        assert result["leg"] == "58"

    def test_stations_list_nonempty(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        assert isinstance(result["stations"], list) and len(result["stations"]) >= 2

    def test_stations_have_required_keys(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        required_keys = {"code", "name", "mile", "lat", "lon", "sched_dep", "sched_arr", "dwell_min"}
        for st in result["stations"]:
            missing = required_keys - set(st.keys())
            assert not missing, f"Station {st.get('code')} missing keys: {missing}"

    def test_geometry_is_linestring(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        geom = result["geometry"]
        assert geom["type"] == "LineString"
        assert len(geom["coordinates"]) >= 2
        for coord in geom["coordinates"][:3]:
            assert len(coord) == 2

    def test_schedule_basis_present(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        sb = result["schedule_basis"]
        assert "kind" in sb and sb["kind"] in ("trip-actual", "generic-scheduled")
        assert "valid_dates" in sb

    def test_units_have_audio_and_dur_s(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        units = result["units"]
        assert len(units) > 0
        for u in units[:5]:
            assert "audio" in u, f"Unit missing 'audio': {u.get('id')}"
            assert "dur_s" in u, f"Unit missing 'dur_s': {u.get('id')}"
            assert u["dur_s"] > 0

    def test_layers_has_required_keys(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        layers = result["layers"]
        for k in ("guide", "lore", "science", "connections", "themes"):
            assert k in layers, f"Missing layer: {k}"

    def test_position_table_present(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        assert "position_table" in result
        assert len(result["position_table"]) > 0

    def test_eta_table_present(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        assert "eta_table" in result

    def test_writes_bundle_json_file(self, tmp_path):
        from pipeline.bundle import build_bundle
        build_bundle("58", tmp_path, proxy=True)
        bundle_path = tmp_path / "leg58" / "bundle.json"
        assert bundle_path.exists()
        loaded = json.loads(bundle_path.read_text())
        assert loaded["leg"] == "58"

    def test_salience_is_integer(self, tmp_path):
        from pipeline.bundle import build_bundle
        result = build_bundle("58", tmp_path, proxy=True)
        for u in result["units"][:20]:
            assert isinstance(u["salience"], int), (
                f"salience must be int, got {type(u['salience'])} on unit {u.get('id')}"
            )


# ── test_validate_bundle ──────────────────────────────────────────────────────

class TestValidateBundle:

    def test_clean_bundle_returns_empty_list(self, tmp_path):
        from pipeline.bundle import validate_bundle
        _leg58_dir, _ = _make_fake_bundle_json(tmp_path)
        problems = validate_bundle("58", outdir=tmp_path)
        assert problems == [], f"Expected no problems, got: {problems}"

    def test_missing_audio_file_flagged(self, tmp_path):
        from pipeline.bundle import validate_bundle
        leg58_dir, bundle = _make_fake_bundle_json(tmp_path)
        bundle["units"][0]["audio"] = "audio/nonexistent.mp3"
        (leg58_dir / "bundle.json").write_text(json.dumps(bundle))
        problems = validate_bundle("58", outdir=tmp_path)
        assert any("audio" in p.lower() or "nonexistent" in p for p in problems), (
            f"Expected audio coverage error, got: {problems}"
        )

    def test_missing_stations_flagged(self, tmp_path):
        from pipeline.bundle import validate_bundle
        leg58_dir, bundle = _make_fake_bundle_json(tmp_path)
        bundle["stations"] = []
        (leg58_dir / "bundle.json").write_text(json.dumps(bundle))
        problems = validate_bundle("58", outdir=tmp_path)
        assert any("station" in p.lower() for p in problems)

    def test_missing_geometry_flagged(self, tmp_path):
        from pipeline.bundle import validate_bundle
        leg58_dir, bundle = _make_fake_bundle_json(tmp_path)
        bundle["geometry"] = {"type": "LineString", "coordinates": []}
        (leg58_dir / "bundle.json").write_text(json.dumps(bundle))
        problems = validate_bundle("58", outdir=tmp_path)
        assert any("geometry" in p.lower() for p in problems)


# ── test_export_position_table ────────────────────────────────────────────────

class TestExportPositionTable:

    def test_monotonic_elapsed_min(self):
        from pipeline.position_table import export_position_table
        rows = export_position_table("58", step_min=5)
        assert len(rows) > 0
        elapsed = [r[0] for r in rows]
        for i in range(1, len(elapsed)):
            assert elapsed[i] > elapsed[i - 1], (
                f"elapsed_min not strictly increasing at index {i}: {elapsed[i-1]} -> {elapsed[i]}"
            )

    def test_miles_nondecreasing(self):
        from pipeline.position_table import export_position_table
        rows = export_position_table("58", step_min=5)
        miles = [r[1] for r in rows]
        for i in range(1, len(miles)):
            assert miles[i] >= miles[i - 1] - 0.1, (
                f"miles decreased at index {i}: {miles[i-1]} -> {miles[i]}"
            )

    def test_first_row_near_mile_zero(self):
        from pipeline.position_table import export_position_table
        rows = export_position_table("58", step_min=5)
        assert rows[0][1] < 10.0, f"First row mile should be near 0, got {rows[0][1]}"

    def test_last_row_near_leg_end(self):
        from pipeline.position_table import export_position_table
        rows = export_position_table("58", step_min=5)
        assert rows[-1][1] > 800, f"Last row mile should be near 934, got {rows[-1][1]}"

    def test_latlon_present_in_each_row(self):
        from pipeline.position_table import export_position_table
        rows = export_position_table("58", step_min=10)
        for i, row in enumerate(rows[:10]):
            assert len(row) == 4, f"Row {i} should have 4 elements: {row}"
            _elapsed, _mile, lat, lon = row
            assert -90 <= lat <= 90, f"Bad lat at row {i}: {lat}"
            assert -180 <= lon <= 180, f"Bad lon at row {i}: {lon}"

    def test_step_min_controls_density(self):
        from pipeline.position_table import export_position_table
        rows_2 = export_position_table("58", step_min=2)
        rows_10 = export_position_table("58", step_min=10)
        assert len(rows_2) > len(rows_10), (
            f"step_min=2 should produce more rows than step_min=10: {len(rows_2)} vs {len(rows_10)}"
        )


# ── test_export_eta_table ─────────────────────────────────────────────────────

class TestExportEtaTable:

    def test_returns_list_with_station_entries(self):
        from pipeline.position_table import export_eta_table
        rows = export_eta_table("58")
        assert isinstance(rows, list)
        assert len(rows) > 0

    def test_p10_le_p50_le_p90(self):
        from pipeline.position_table import export_eta_table
        rows = export_eta_table("58")
        for row in rows:
            assert row["p10_min"] <= row["p50_min"], (
                f"p10 > p50 for {row['station_code']}: {row['p10_min']} > {row['p50_min']}"
            )
            assert row["p50_min"] <= row["p90_min"], (
                f"p50 > p90 for {row['station_code']}: {row['p50_min']} > {row['p90_min']}"
            )

    def test_each_row_has_required_keys(self):
        from pipeline.position_table import export_eta_table
        rows = export_eta_table("58")
        for row in rows:
            for k in ("station_code", "p10_min", "p50_min", "p90_min"):
                assert k in row, f"Missing key '{k}' in: {row}"

    def test_station_codes_on_leg(self):
        from pipeline.position_table import export_eta_table
        rows = export_eta_table("58")
        codes = {r["station_code"] for r in rows}
        assert "JAN" in codes or "MEM" in codes, f"Expected JAN or MEM in {codes}"
