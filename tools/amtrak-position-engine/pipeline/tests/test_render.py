"""Tests for pipeline/render.py — Chirp3-HD MP3 render, content-hash cache, cost estimate.

All HTTP is mocked — no live calls in pytest.
"""
import pathlib
import pipeline.render as render


# ---------------------------------------------------------------------------
# render_unit: content-hash cache
# ---------------------------------------------------------------------------

def test_render_unit_caches_by_content_hash(tmp_path, monkeypatch):
    """synth should be called only once across two calls with the same unit/voice."""
    calls = []

    def fake_synth(text, cp, voice="x"):
        calls.append(text)
        return b"FAKEMP3BYTES"

    monkeypatch.setattr(render, "synth", fake_synth)

    u = {"id": "w1", "text": "Raton Pass."}
    r1 = render.render_unit(u, {}, tmp_path, "v")
    r2 = render.render_unit(u, {}, tmp_path, "v")

    assert r1["file"].endswith(".mp3"), f"expected .mp3 extension, got {r1['file']}"
    assert r2["cached"] is True, "second call should be cached"
    assert len(calls) == 1, f"synth should be called once, got {len(calls)}"


def test_render_unit_first_call_not_cached(tmp_path, monkeypatch):
    """First render_unit call is NOT cached."""
    monkeypatch.setattr(render, "synth", lambda text, cp, voice="x": b"BYTES")

    u = {"id": "u1", "text": "Hello world."}
    r = render.render_unit(u, {}, tmp_path, "v")
    assert r["cached"] is False


def test_render_unit_file_written(tmp_path, monkeypatch):
    """render_unit actually writes the file to disk."""
    payload = b"FAKEMP3CONTENT"
    monkeypatch.setattr(render, "synth", lambda text, cp, voice="x": payload)

    u = {"id": "u2", "text": "Test content."}
    r = render.render_unit(u, {}, tmp_path, "v")

    out_file = pathlib.Path(r["file"])
    assert out_file.exists(), "output file should exist on disk"
    assert out_file.read_bytes() == payload


def test_render_unit_different_voice_different_hash(tmp_path, monkeypatch):
    """Different voice → different hash → different file → synth called twice."""
    calls = []
    monkeypatch.setattr(render, "synth", lambda text, cp, voice="x": (calls.append(voice) or b"BYTES"))

    u = {"id": "u3", "text": "Same text."}
    r1 = render.render_unit(u, {}, tmp_path, "voice-A")
    r2 = render.render_unit(u, {}, tmp_path, "voice-B")

    assert r1["file"] != r2["file"], "different voices should produce different cache files"
    assert len(calls) == 2


def test_render_unit_returns_bytes_count(tmp_path, monkeypatch):
    """render_unit result includes 'bytes' (len of audio data) and 'chars'."""
    payload = b"X" * 500
    monkeypatch.setattr(render, "synth", lambda text, cp, voice="x": payload)

    u = {"id": "u4", "text": "A" * 42}
    r = render.render_unit(u, {}, tmp_path, "v")

    assert r["bytes"] == 500
    assert r["chars"] == 42


def test_render_unit_outdir_created(tmp_path, monkeypatch):
    """render_unit creates the output directory if it doesn't exist."""
    monkeypatch.setattr(render, "synth", lambda text, cp, voice="x": b"BYTES")

    new_dir = tmp_path / "nested" / "subdir"
    u = {"id": "u5", "text": "Hello."}
    render.render_unit(u, {}, new_dir, "v")

    assert new_dir.exists()


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------

def test_estimate_cost_scales_with_chars():
    """estimate_cost returns correct char count and non-negative usd range."""
    narration = {"3": [{"text": "x" * 1000}]}
    e = render.estimate_cost(narration)

    assert e["chars"] == 1000
    assert e["usd_high"] >= e["usd_low"] >= 0


def test_estimate_cost_sums_across_legs():
    """estimate_cost sums chars across all legs and units."""
    narration = {
        "3": [{"text": "a" * 600}, {"text": "b" * 400}],
        "58": [{"text": "c" * 1000}],
    }
    e = render.estimate_cost(narration)
    assert e["chars"] == 2000


def test_estimate_cost_zero_chars():
    """estimate_cost handles empty narration gracefully."""
    e = render.estimate_cost({})
    assert e["chars"] == 0
    assert e["usd_low"] == 0.0
    assert e["usd_high"] == 0.0


def test_estimate_cost_rate_range():
    """estimate_cost uses the $30/1M–$45/1M Chirp3 rate range."""
    narration = {"leg": [{"text": "x" * 1_000_000}]}
    e = render.estimate_cost(narration)
    assert e["chars"] == 1_000_000
    assert abs(e["usd_low"] - 30.0) < 0.01
    assert abs(e["usd_high"] - 45.0) < 0.01


def test_estimate_cost_skips_missing_text():
    """estimate_cost gracefully skips units without a 'text' field."""
    narration = {"3": [{"text": "a" * 100}, {"id": "no-text-unit"}]}
    e = render.estimate_cost(narration)
    assert e["chars"] == 100
