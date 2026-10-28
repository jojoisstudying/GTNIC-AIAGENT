"""Tests #10: pose yang di-reject tidak boleh membuat run loop; regenerate endpoint & task."""
import io
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import api, config
from src.core.context import create_run_context
from src.core.db import Base, Run
from src.carousel.tools import asset_library, cloudflare_pose_generator as cpg

BRAND = {"company": "Test Brand"}


def _png(size=(200, 300), transparent=True) -> bytes:
    img = Image.new("RGBA", size, (0, 0, 0, 0) if transparent else (10, 10, 10, 255))
    img.paste((200, 50, 50, 255), (50, 50, 150, 250))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def gen_env(tmp_path: Path, monkeypatch):
    """Isolasi: ROOT, asset DB, Cloudflare call, dan rembg dipalsukan."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(asset_library, "DB", tmp_path / "assets.db")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    ref_dir = tmp_path / "data" / "people" / "p1"
    ref_dir.mkdir(parents=True)
    (ref_dir / "reference.png").write_bytes(_png(transparent=False))

    calls = {"n": 0}

    class FakeResp:
        ok = True
        status_code = 200
        text = ""
        headers: dict = {}

        def raise_for_status(self):
            return None

    def fake_post(*a, **kw):
        calls["n"] += 1
        return FakeResp()

    def fake_session_request(self, method, url, **kw):  # jalur ctx.http.request (HttpClient)
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(cpg.requests, "post", fake_post)
    monkeypatch.setattr(cpg.requests.Session, "request", fake_session_request)
    monkeypatch.setattr(cpg, "_extract_image", lambda r: b"raw")
    monkeypatch.setattr(cpg, "_remove_background", lambda b: _png())
    return calls


def test_rejected_pose_is_replaced_not_returned_from_cache(gen_env):
    calls = gen_env
    a = cpg.generate_pose("p1", "senyum")
    assert a["status"] == "pending_review" and calls["n"] == 1

    asset_library.set_status(a["id"], "rejected")

    b = cpg.generate_pose("p1", "senyum")  # tanpa force, seperti yang dilakukan designer saat resume
    assert b["id"] != a["id"]
    assert b["status"] == "pending_review"
    assert calls["n"] == 2

    # resume lagi sebelum b direview: pakai kandidat yang sama, jangan bayar generate lagi
    c = cpg.generate_pose("p1", "senyum")
    assert c["id"] == b["id"] and c["status"] == "pending_review"
    assert calls["n"] == 2

    # force tetap membuat varian baru
    d = cpg.generate_pose("p1", "senyum", force=True)
    assert d["id"] not in {a["id"], b["id"]}
    assert calls["n"] == 3


def test_approved_cache_still_reused(gen_env):
    calls = gen_env
    a = cpg.generate_pose("p1", "senyum")
    asset_library.set_status(a["id"], "approved")
    again = cpg.generate_pose("p1", "senyum")
    assert again["id"] == a["id"] and calls["n"] == 1


# ---------- API ----------

@pytest.fixture()
def api_env(gen_env, tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(api, "SessionLocal", factory)
    monkeypatch.setattr(api.pipeline, "load_brand", lambda: BRAND)
    monkeypatch.setattr(
        api, "create_run_context",
        lambda topic, brand, **kw: create_run_context(topic, brand, session_factory=factory, **kw),
    )
    return factory


def _run(factory, status):
    ctx = create_run_context("topik", BRAND, session_factory=factory)
    rid = ctx.run_id
    ctx.close()
    with factory() as s:
        s.get(Run, rid).status = status
        s.commit()
    return rid


def _rejected_asset(run_id=None):
    a = cpg.generate_pose("p1", "senyum", ctx=None)
    asset_library.add_asset(a["path"], ["senyum"], "x", status="rejected", person_id="p1",
                            model="m", run_id=run_id, kind="pose", cache_key=a["cache_key"])
    return a["id"]


def test_regenerate_validations(api_env):
    req = api.RegeneratePoseRequest()
    with pytest.raises(HTTPException) as e:
        api.regenerate_pose_endpoint(9999, req, BackgroundTasks())
    assert e.value.status_code == 404

    aid = _rejected_asset()
    asset_library.add_asset(
        asset_library.get_asset(aid)["path"], ["senyum"], "x", status="approved",
        person_id="p1", model="m", kind="pose")
    with pytest.raises(HTTPException) as e:
        api.regenerate_pose_endpoint(aid, req, BackgroundTasks())
    assert e.value.status_code == 400  # bukan rejected


def test_regenerate_links_waiting_run_and_blocks_double_click(api_env):
    factory = api_env
    run_id = _run(factory, "awaiting_approval")
    aid = _rejected_asset(run_id)

    bg = BackgroundTasks()
    res = api.regenerate_pose_endpoint(aid, api.RegeneratePoseRequest(), bg)
    assert res["mode"] == "run" and res["run_id"] == run_id
    assert len(bg.tasks) == 1
    with factory() as s:
        assert s.get(Run, run_id).status == "running"

    with pytest.raises(HTTPException) as e:  # klik kedua saat run masih diproses
        api.regenerate_pose_endpoint(aid, api.RegeneratePoseRequest(), BackgroundTasks())
    assert e.value.status_code == 409


def test_regenerate_standalone_when_run_not_waiting(api_env):
    factory = api_env
    run_id = _run(factory, "ok")
    aid = _rejected_asset(run_id)
    bg = BackgroundTasks()
    res = api.regenerate_pose_endpoint(aid, api.RegeneratePoseRequest(), bg)
    assert res["mode"] == "standalone" and res["run_id"] is None
    with factory() as s:
        assert s.get(Run, run_id).status == "ok"  # run lama tidak disentuh


def test_task_success_creates_candidate_then_resumes(api_env, monkeypatch):
    factory = api_env
    run_id = _run(factory, "running")
    aid = _rejected_asset(run_id)
    resumed = []
    monkeypatch.setattr(api, "_execute_resume_task", lambda rid: resumed.append(rid))

    api._execute_regenerate_task(run_id, aid, "senyum", "p1", "")

    assert resumed == [run_id]
    pending = asset_library.list_assets(status="pending_review")
    assert len(pending) == 1 and pending[0]["id"] != aid


def test_task_failure_returns_run_to_awaiting_assets(api_env, monkeypatch):
    factory = api_env
    run_id = _run(factory, "running")
    aid = _rejected_asset(run_id)
    resumed = []
    monkeypatch.setattr(api, "_execute_resume_task", lambda rid: resumed.append(rid))

    def boom(*a, **kw):
        raise RuntimeError("cloudflare down")

    monkeypatch.setattr(cpg, "generate_pose", boom)
    api._execute_regenerate_task(run_id, aid, "senyum", "p1", "")

    assert resumed == []
    with factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "awaiting_assets"
        assert "cloudflare down" in run.error