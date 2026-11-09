"""Alur persetujuan publikasi, pusat otomatisasi, pembatalan generasi, analytics per konten.

Fokus pada invariant yang diminta produk:
- tidak ada publikasi tanpa persetujuan;
- persetujuan tidak diminta berulang;
- klik ganda / retry tidak menghasilkan dua postingan;
- pembatalan menghentikan pekerjaan lanjutan dan tidak menyimpan hasil sebagai konten sukses;
- metrik yang tidak didukung API tetap NULL (bukan 0).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import api, automation_api, config
from src.core import automation, cancellation, publication_service as ps
from src.core.context import create_run_context
from src.core.db import (AutomationEvent, Base, ContentStrategyItem, Design, PostAnalytics,
                         PostAnalyticsSnapshot, Publication, Run, utc_now)

BRAND = {"company": "Test Brand", "hashtags": ["#tes"]}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    out_dir = tmp_path / "output"
    (out_dir / "reels").mkdir(parents=True)
    monkeypatch.setattr(config, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(api, "SessionLocal", factory)
    monkeypatch.setattr(automation_api, "SessionLocal", factory)
    monkeypatch.setattr(api.pipeline, "load_brand", lambda: BRAND)
    monkeypatch.setattr(api, "create_run_context",
                        lambda topic, brand, **kw: create_run_context(topic, brand, session_factory=factory, **kw))

    ctx = create_run_context("Topik Uji", BRAND, session_factory=factory)
    run_id = ctx.run_id
    ctx.close()
    return factory, run_id, out_dir


def _carousel_run(factory, run_id, out_dir, slides=3):
    slides_dir = out_dir / "runs" / run_id / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(slides):
        p = slides_dir / f"slide_{i + 1}.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
        paths.append(str(p))
    design = {"ok": True, "slides": [{"index": i + 1, "path": p, "issues": []}
                                     for i, p in enumerate(paths)]}
    from src.core.db import Plan
    with factory() as s:
        s.add(Plan(run_id=run_id, version=1, ok=True,
                   plan_json=json.dumps({"caption": "Caption uji", "hashtags": ["tips", "umkm"]})))
        s.add(Design(run_id=run_id, version=1, ok=True, result_json=json.dumps(design)))
        run = s.get(Run, run_id)
        run.status = "ok"
        s.commit()
    return paths


# ---------------------------------------------------------------------------
# 1. Alur persetujuan publikasi
# ---------------------------------------------------------------------------

def test_prepare_creates_pending_approval_without_calling_meta(env, monkeypatch):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    monkeypatch.setattr("src.tools.instagram.publish_carousel",
                        lambda *a, **k: pytest.fail("tidak boleh memanggil Instagram sebelum disetujui"))

    res = automation_api.prepare_publication(run_id, automation_api.PreparePublicationRequest(), request=_req())

    pub = res["publication"]
    assert res["requires_approval"] is True
    assert pub["status"] == "pending_approval" and pub["status_label"] == "Menunggu persetujuan"
    assert pub["can_publish"] and pub["can_cancel"] and pub["can_edit"]
    assert pub["hashtags"] == ["#tips", "#umkm"]
    assert "Caption uji" in pub["caption"] and "#tips" in pub["caption"]
    with factory() as s:
        assert s.query(Publication).count() == 1


def _req(name="tester"):
    class R:
        headers = {"X-User-Name": name}

        class client:
            host = "127.0.0.1"
    return R()


def test_approve_publishes_once_and_is_idempotent(env, monkeypatch):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "Halo", "hashtags": []},
                                media_type="carousel", image_urls=["https://cdn.test/a.jpg",
                                                                   "https://cdn.test/b.jpg"])
        pub_id = pub.id

    calls = []
    monkeypatch.setattr("src.tools.instagram.publish_carousel",
                        lambda urls, cap, ctx=None: calls.append(urls) or "IG_MEDIA_1")
    monkeypatch.setattr("src.tools.instagram.get_media_metrics",
                        lambda mid, ctx=None: {"permalink": "https://instagr.am/p/1"})

    first = automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest())
    assert first["ok"] is True and first["status"] == "published" and first["media_id"] == "IG_MEDIA_1"

    # Klik kedua: tidak memposting ulang, tidak meminta persetujuan lagi.
    second = automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest())
    assert second["ok"] is True and second["already_published"] is True
    assert len(calls) == 1
    with factory() as s:
        pubs = s.query(Publication).all()
        assert len(pubs) == 1 and pubs[0].status == "published"
        assert pubs[0].permalink == "https://instagr.am/p/1"
        analytics = s.query(PostAnalytics).one()
        assert analytics.publication_id == pub_id and analytics.reach is None  # belum diambil, bukan 0
        assert analytics.ingestion_status == "pending"


def test_cannot_publish_without_approval(env, monkeypatch):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "x"}, media_type="carousel",
                                image_urls=["https://cdn.test/a.jpg"])
        pub_id = pub.id
    monkeypatch.setattr("src.tools.instagram.publish_carousel",
                        lambda *a, **k: pytest.fail("tidak boleh posting"))
    with pytest.raises(HTTPException) as exc:
        automation_api.publish_now(pub_id)
    assert exc.value.status_code == 409 and "belum disetujui" in exc.value.detail


def test_claim_is_atomic_so_double_click_publishes_once(env):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "x"}, media_type="carousel",
                                image_urls=["https://cdn.test/a.jpg"], require_approval=False)
        ps.approve(s, pub, actor="tester")
        pub = s.get(Publication, pub.id)
        pub.status = ps.SCHEDULED
        s.commit()
        first_token = ps.claim(s, pub)          # pemanggil pertama dapat hak eksekusi
        s.refresh(pub)
        with pytest.raises(ps.PublicationError) as exc:
            ps.claim(s, pub)                    # klik/retry kedua ditolak
    assert first_token and exc.value.status_code == 409


def test_scheduled_approval_does_not_publish_immediately(env, monkeypatch):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "x"}, media_type="carousel",
                                image_urls=["https://cdn.test/a.jpg"])
        pub_id = pub.id
    monkeypatch.setattr("src.tools.instagram.publish_carousel",
                        lambda *a, **k: pytest.fail("belum waktunya tayang"))
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    res = automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest(scheduled_for=future))
    assert res["ok"] is True and res["status"] == "scheduled"
    assert res["publication"]["scheduled_for"] is not None
    with factory() as s:
        assert s.get(Publication, pub_id).status == "scheduled"


def test_cancel_blocks_publishing_and_marks_row(env, monkeypatch):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "x"}, media_type="carousel",
                                image_urls=["https://cdn.test/a.jpg"])
        pub_id = pub.id
    monkeypatch.setattr("src.tools.instagram.publish_carousel",
                        lambda *a, **k: pytest.fail("dibatalkan, jangan posting"))

    res = automation_api.cancel_publication(pub_id, request=_req())
    assert res["ok"] is True
    assert res["publication"]["status"] == "cancelled"
    assert res["publication"]["status_label"] == "Dibatalkan"
    assert res["publication"]["can_cancel"] is False and res["publication"]["can_publish"] is False

    with pytest.raises(HTTPException) as exc:
        automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest())
    assert exc.value.status_code == 409


def test_cannot_cancel_after_published(env):
    factory, run_id, out_dir = env
    with factory() as s:
        s.add(Publication(run_id=run_id, status="published", media_id="IG9", caption="c",
                          image_urls_json="[]", platform="instagram"))
        s.commit()
        pub_id = s.query(Publication).one().id
    with pytest.raises(HTTPException) as exc:
        automation_api.cancel_publication(pub_id, request=_req())
    assert exc.value.status_code == 409 and "sudah tayang" in exc.value.detail


def test_edit_caption_hashtags_schedule_and_reject_when_published(env):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "lama", "hashtags": ["a"]},
                                media_type="carousel", image_urls=["https://cdn.test/a.jpg"])
        pub_id = pub.id
    res = automation_api.edit_publication(pub_id, automation_api.PublicationEditRequest(
        caption="caption baru", hashtags=["#Promo", "umkm", "umkm"], media_type="image"))
    body = res["publication"]["caption"]
    assert "caption baru" in body and "#Promo" in body and "#umkm" in body
    assert res["publication"]["hashtags"] == ["#Promo", "#umkm"]   # dinormalisasi & unik
    assert res["publication"]["media_type"] == "image"

    with factory() as s:
        pub = s.get(Publication, pub_id)
        pub.status = "published"
        s.commit()
    with pytest.raises(HTTPException) as exc:
        automation_api.edit_publication(pub_id, automation_api.PublicationEditRequest(caption="x"))
    assert exc.value.status_code == 409


def test_caption_and_hashtags_are_normalized_and_capped():
    assert ps.normalize_hashtags("tips, #umkm  promo") == ["#tips", "#umkm", "#promo"]
    assert ps.normalize_hashtags("#a #A") == ["#a"]            # dedupe case-insensitive
    long_caption = "x" * 3000
    composed = ps.compose_caption(long_caption, ["#" + "t" * 10] * 40)
    assert len(composed) <= ps.CAPTION_MAX


def test_stale_publishing_claim_is_released(env):
    factory, run_id, out_dir = env
    with factory() as s:
        s.add(Publication(run_id=run_id, status="publishing", platform="instagram",
                          caption="c", image_urls_json="[]",
                          claimed_at=utc_now() - timedelta(hours=2), claim_token="tok"))
        s.commit()
    with factory() as s:
        assert ps.release_stale_claims(s, older_than_minutes=30) == 1
        pub = s.query(Publication).one()
        assert pub.status == "failed" and "sebelum menghubungi Instagram" in pub.error


def test_intent_row_is_never_auto_retried(env, monkeypatch):
    """Baris 'intent' = API Meta mungkin sudah dipanggil; retry otomatis bisa menghasilkan 2 postingan."""
    factory, run_id, out_dir = env
    with factory() as s:
        s.add(Publication(run_id=run_id, status="intent", platform="instagram", caption="c",
                          image_urls_json="[]", approved_at=utc_now(), approved_by="tester",
                          scheduled_for=utc_now() - timedelta(minutes=5)))
        s.commit()
    from src.core import scheduler
    monkeypatch.setattr(automation, "automation_active", lambda session: True)
    assert scheduler.run_once(factory, lambda rid: pytest.fail("tidak boleh retry"),
                              now=datetime.now(timezone.utc)) == []


# ---------------------------------------------------------------------------
# 2. Pusat Otomatisasi
# ---------------------------------------------------------------------------

def test_automation_center_returns_settings_summary_and_queues(env):
    factory, run_id, _ = env
    with factory() as s:
        s.add(ContentStrategyItem(plan_date="2026-11-07", topic="A", format="carousel",
                                  content_pillar="Tips", objective="Edukasi",
                                  target_segment="Umum", scheduled_slot="09:00", status="approved"))
        s.add(Publication(run_id="run-x", status="pending_approval", platform="instagram",
                          caption="c", image_urls_json="[]"))
        s.add(Publication(run_id="run-y", status="scheduled", platform="instagram",
                          caption="c", image_urls_json="[]",
                          scheduled_for=utc_now() + timedelta(hours=3)))
        s.commit()

    payload = automation_api.get_automation_center()
    assert payload["settings"]["publishing_mode"] in ("autopilot", "review")
    assert payload["settings"]["platforms"] == ["instagram"]
    assert payload["summary"]["awaiting_approval"] == 1
    assert payload["summary"]["scheduled"] == 1
    assert len(payload["pending_approvals"]) == 1 and len(payload["scheduled"]) == 1
    assert payload["next_slot"] is not None


def test_automation_settings_update_validates_and_persists(env):
    factory, run_id, _ = env
    payload = automation_api.update_automation_center(automation_api.AutomationUpdateRequest(
        enabled=True, slots=["19:00", "7:30", "19:00"], posting_days=[1, 3, 5],
        frequency_per_week=3, content_formats=["carousel", "video"], require_approval=True,
        platforms=["instagram", "facebook"]), request=_req())
    assert payload["settings"]["is_running"] is True
    assert payload["settings"]["slots"] == ["07:30", "19:00"]
    assert payload["settings"]["posting_days"] == [1, 3, 5]
    assert payload["settings"]["platforms"] == ["instagram", "facebook"]
    assert payload["settings"]["available_platforms"][1]["available"] is False

    for bad in ({"slots": ["99:00"]}, {"posting_days": [0]}, {"posting_days": []},
                {"frequency_per_week": 99}, {"platforms": ["myspace"]}):
        with pytest.raises(HTTPException) as exc:
            automation_api.update_automation_center(automation_api.AutomationUpdateRequest(**bad), request=_req())
        assert exc.value.status_code == 400


def test_pause_resume_stop_are_persisted_and_stop_cancels_scheduled(env):
    factory, run_id, _ = env
    with factory() as s:
        s.add(Publication(run_id="run-z", status="scheduled", platform="instagram",
                          caption="c", image_urls_json="[]", approved_at=utc_now()))
        s.commit()

    assert automation_api.pause_automation(request=_req())["settings"]["state"] == "paused"
    assert automation_api.resume_automation(request=_req())["settings"]["state"] == "running"

    stopped = automation_api.stop_automation(request=_req())
    assert stopped["settings"]["state"] == "stopped"
    assert stopped["settings"]["enabled"] is False
    assert stopped["summary"]["cancelled"] == 1
    assert stopped["summary"]["scheduled"] == 0

    with factory() as s:
        row = automation._ensure(s)
        assert row.state == "stopped" and row.enabled is False
        actions = [e.action for e in s.scalars(select(AutomationEvent).order_by(AutomationEvent.id))]
    assert actions == ["paused", "resumed", "stopped"]   # tiap kontrol tercatat


def test_paused_automation_does_not_publish_scheduled(env, monkeypatch):
    factory, run_id, _ = env
    with factory() as s:
        s.add(Publication(run_id="run-p", status="scheduled", platform="instagram",
                          caption="c", image_urls_json="[]", approved_at=utc_now(),
                          scheduled_for=utc_now() - timedelta(minutes=1)))
        s.commit()
    automation.pause(automation._ensure_session(factory) if hasattr(automation, "_ensure_session") else None) \
        if False else None
    with factory() as s:
        automation.pause(s, actor="tester")
    from src.core import scheduler
    monkeypatch.setattr("src.agents.publisher.execute_publication",
                        lambda *a, **k: pytest.fail("otomatisasi dijeda"))
    assert scheduler.run_once(factory, lambda rid: pytest.fail("tidak boleh"),
                              now=datetime.now(timezone.utc)) == []


def test_next_slot_respects_days_and_timezone(env):
    factory, run_id, _ = env
    with factory() as s:
        row = automation._ensure(s)
        row.posting_days_json = json.dumps([1])       # hanya Senin
        row.slots_json = json.dumps(["09:00"])
        row.timezone = "Asia/Jakarta"
        s.commit()
    with factory() as s:
        now = datetime(2026, 11, 3, 0, 0, tzinfo=timezone.utc)   # Selasa 07:00 WIB
        nxt = automation.next_slot_after(s, now=now)
    # Senin berikutnya 09:00 WIB == 02:00 UTC
    assert nxt == datetime(2026, 11, 9, 2, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 3. Pembatalan generasi
# ---------------------------------------------------------------------------

def test_cancel_run_marks_cancelled_and_reports_no_retry(env):
    factory, run_id, _ = env
    res = automation_api.cancel_run(run_id, request=_req())
    assert res["status"] == "cancelled"
    with factory() as s:
        assert s.get(Run, run_id).status == "cancelled"
    assert cancellation.is_cancelled(run_id) is True
    # Idempoten
    assert automation_api.cancel_run(run_id, request=_req())["already"] is True
    cancellation.clear(run_id)


def test_cancel_finished_run_is_refused(env):
    factory, run_id, _ = env
    with factory() as s:
        s.get(Run, run_id).status = "ok"
        s.commit()
    res = automation_api.cancel_run(run_id, request=_req())
    assert res["ok"] is False and "tidak bisa dibatalkan" in res["message"]


def test_cancelled_pipeline_does_not_persist_design(env, monkeypatch):
    """Pembatalan di tengah jalan: run jadi 'cancelled', bukan 'failed', dan tidak ada desain tersimpan."""
    factory, run_id, out_dir = env
    ctx = create_run_context("Topik Batal", BRAND, run_id=run_id, session_factory=factory)
    cancellation.request_cancel(run_id)
    try:
        from src.carousel import pipeline as carousel_pipeline
        monkeypatch.setattr(carousel_pipeline, "load_brand", lambda: BRAND)
        # include_design=False pun sudah cukup: cek pertama di awal pipeline langsung membatalkan.
        out = carousel_pipeline.run("Topik Batal", fresh=False, ctx=ctx, include_design=False,
                                    on_step=lambda *_: None)
        assert out.get("cancelled") is True
    finally:
        ctx.close()
        cancellation.clear(run_id)
    with factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "cancelled" and run.error is None
        assert s.query(Design).count() == 0


def test_cancellation_flag_is_cooperative_and_idempotent():
    cancellation.clear("run-flag")
    assert cancellation.is_cancelled("run-flag") is False
    assert cancellation.request_cancel("run-flag") is True
    assert cancellation.request_cancel("run-flag") is False   # kedua kali: sudah ditandai
    with pytest.raises(cancellation.GenerationCancelled):
        cancellation.raise_if_cancelled("run-flag")
    cancellation.clear("run-flag")
    assert cancellation.is_cancelled("run-flag") is False
    # run lain tidak terpengaruh
    assert cancellation.is_cancelled("run-other") is False


# ---------------------------------------------------------------------------
# 4. Analytics per konten
# ---------------------------------------------------------------------------

def _published(factory, run_id, media_id="IG_ANALYTICS"):
    with factory() as s:
        pub = Publication(run_id=run_id, status="published", media_id=media_id,
                          platform="instagram", caption="c", image_urls_json="[]",
                          media_type="carousel", published_at=utc_now())
        s.add(pub)
        s.commit()
        return pub.id


def test_analytics_detail_separates_missing_from_zero(env):
    factory, run_id, _ = env
    pub_id = _published(factory, run_id)
    from src.core.analytics_ingest import ingest_publication
    with factory() as s:
        pub = s.get(Publication, pub_id)
        metrics = ingest_publication(s, pub, lambda mid: {
            "likes": 0, "comments": 0, "reach": 0, "saves": 0, "shares": None,
            "views": None, "profile_visits": None, "permalink": "https://instagr.am/p/1",
            "metrics_available": ["reach", "saved", "shares"], "media_type": "CAROUSEL_ALBUM",
        })
    assert metrics["likes"] == 0

    detail = automation_api.analytics_publication_detail(pub_id)
    assert detail["media_id"] == "IG_ANALYTICS"
    assert detail["metrics"]["reach"] == 0            # benar-benar nol
    assert detail["metrics"]["shares"] is None        # belum tersedia
    assert detail["metrics"]["engagement_rate"] is None   # reach 0 -> rasio tak bisa dihitung
    assert detail["available_metrics"]["reach"] is True
    assert detail["available_metrics"]["shares"] is False
    assert len(detail["history"]) == 1


def test_analytics_history_accumulates_snapshots(env):
    factory, run_id, _ = env
    pub_id = _published(factory, run_id, media_id="IG_HIST")
    from src.core.analytics_ingest import ingest_publication
    for likes, reach in ((1, 10), (5, 40)):
        with factory() as s:
            pub = s.get(Publication, pub_id)
            ingest_publication(s, pub, lambda mid, l=likes, r=reach: {
                "likes": l, "comments": 0, "reach": r, "saves": 0, "shares": 0,
                "metrics_available": ["reach", "likes"]})
    detail = automation_api.analytics_publication_detail(pub_id)
    assert len(detail["history"]) == 2
    assert detail["history"][-1]["reach"] == 40
    assert detail["metrics"]["engagement_rate"] == round(5 / 40 * 100, 2)
    with factory() as s:
        assert s.query(PostAnalyticsSnapshot).count() == 2


def test_analytics_requires_published_media_id(env):
    factory, run_id, _ = env
    with factory() as s:
        pub = Publication(run_id=run_id, status="pending_approval", platform="instagram",
                          caption="c", image_urls_json="[]")
        s.add(pub)
        s.commit()
        pub_id = pub.id
    with pytest.raises(HTTPException) as exc:
        automation_api.analytics_publication_detail(pub_id)
    assert exc.value.status_code == 409 and "belum punya ID" in exc.value.detail

    listed = automation_api.analytics_publications()
    assert listed["total"] == 0        # konten yang belum tayang tidak bisa dipilih


def test_analytics_list_only_shows_real_published_posts(env):
    factory, run_id, _ = env
    _published(factory, run_id, media_id="IG_A")
    with factory() as s:
        s.add(Publication(run_id="r2", status="failed", platform="instagram", caption="c",
                          image_urls_json="[]"))
        s.commit()
    listed = automation_api.analytics_publications()
    assert listed["total"] == 1
    assert listed["items"][0]["media_id"] == "IG_A"
    assert listed["items"][0]["metrics"]["available"] is False   # belum ada pengambilan metrik


# ---------------------------------------------------------------------------
# 6. Ringkasan minggu, batch approve, dan status live
# ---------------------------------------------------------------------------

def _req():
    from starlette.requests import Request
    return Request({"type": "http", "headers": [], "method": "POST", "path": "/"})


def test_week_overview_merges_calendar_and_publications_without_duplicates(env):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        s.add(ContentStrategyItem(plan_date="2026-11-10", topic="Senin pagi", format="carousel",
                                  content_pillar="Edukasi", objective="Edukasi", target_segment="Umum",
                                  scheduled_slot="09:00 WIB", status="draft"))
        s.add(ContentStrategyItem(plan_date="2026-11-11", topic="Selasa video", format="video",
                                  content_pillar="Edukasi", objective="Edukasi", target_segment="Umum",
                                  scheduled_slot="13:00 WIB", status="awaiting_approval", run_id=run_id))
        s.commit()
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "Caption"}, media_type="carousel",
                                image_urls=["https://cdn.test/a.jpg"])
        pub_id = pub.id

    with factory() as s:
        rows = automation_api.week_overview(s)

    # Item kalender yang sudah punya baris publikasi tidak boleh muncul dua kali:
    # "Selasa video" terhubung ke run yang punya publikasi, jadi hanya baris publikasi
    # yang dipakai (bukan juga baris kalender).
    topics = [r["topic"] for r in rows]
    assert topics.count("Selasa video") == 1
    selasa = [r for r in rows if r["topic"] == "Selasa video"]
    assert selasa[0]["kind"] == "publication"
    assert sum(1 for r in rows if r["kind"] == "publication" and r["ref_id"] == pub_id) == 1
    # Item tanpa run tetap muncul sebagai baris kalender.
    senin = [r for r in rows if r["topic"] == "Senin pagi"]
    assert len(senin) == 1 and senin[0]["kind"] == "calendar"
    # Slot ditampilkan tanpa label zona waktu.
    assert senin[0]["slot"] == "09:00" and senin[0]["can_approve"] is True


def test_approve_all_is_idempotent_and_never_calls_meta(env, monkeypatch):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        s.add(ContentStrategyItem(plan_date="2026-11-10", topic="Ide A", format="carousel",
                                  content_pillar="Edukasi", objective="Edukasi", target_segment="Umum",
                                  scheduled_slot="09:00 WIB", status="draft"))
        s.commit()
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "Caption"}, media_type="carousel",
                                image_urls=["https://cdn.test/a.jpg"])
        pub_id = pub.id

    calls = []
    monkeypatch.setattr("src.tools.instagram.publish_image",
                        lambda *a, **k: calls.append("image") or "IG")
    monkeypatch.setattr("src.tools.instagram.publish_carousel",
                        lambda *a, **k: calls.append("carousel") or "IG")

    first = automation_api.approve_all(request=_req())
    assert first["approved_calendar_items"] == 1
    assert first["approved_publications"] == 1
    assert calls == []      # batch approve TIDAK mempublikasikan apa pun

    # Publikasi menjadi terjadwal (bukan published) dan punya waktu tayang.
    with factory() as s:
        pub = s.get(Publication, pub_id)
        assert pub.status == ps.SCHEDULED and pub.media_id is None
        assert pub.scheduled_for is not None
        assert pub.approved_at is not None

    second = automation_api.approve_all(request=_req())
    assert second["approved_calendar_items"] == 0
    assert second["approved_publications"] == 0
    assert calls == []


def test_live_status_ignores_stale_running_runs(env):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    with factory() as s:
        run = s.get(Run, run_id)
        run.status = "running"
        run.started_at = old
        s.commit()

    with factory() as s:
        live = automation_api.live_status(s)
    assert live["active_runs"] == []      # run macet tidak ditampilkan sebagai proses live
    assert live["stale_runs"] == 1
    assert live["idle"] is True


def test_edit_calendar_topic_validates_and_blocks_published(env):
    factory, run_id, _ = env
    with factory() as s:
        item = ContentStrategyItem(plan_date="2026-11-10", topic="Topik lama yang panjang", format="carousel",
                                   content_pillar="Edukasi", objective="Edukasi", target_segment="Umum",
                                   scheduled_slot="09:00 WIB", status="draft")
        s.add(item)
        s.commit()
        item_id = item.id

    res = api.update_strategy_item_endpoint(item_id, api.StrategyItemAction(topic="  Topik baru yang lebih jelas  "))
    assert res["status"] == "ok"
    with factory() as s:
        assert s.get(ContentStrategyItem, item_id).topic == "Topik baru yang lebih jelas"

    with pytest.raises(HTTPException) as exc:
        api.update_strategy_item_endpoint(item_id, api.StrategyItemAction(topic="pendek"))
    assert exc.value.status_code == 400

    with factory() as s:
        s.get(ContentStrategyItem, item_id).status = "published"
        s.commit()
    with pytest.raises(HTTPException) as exc:
        api.update_strategy_item_endpoint(item_id, api.StrategyItemAction(topic="Topik lain yang cukup panjang"))
    assert exc.value.status_code == 409


def test_individual_approval_with_valid_schedule(env):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "test caption"}, media_type="carousel",
                                image_urls=["https://cdn.test/1.jpg"])
        pub_id = pub.id
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    res = automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest(publish_now=False, scheduled_for=future))
    assert res["ok"] is True
    assert res["status"] == "scheduled"
    with factory() as s:
        p = s.get(Publication, pub_id)
        assert p.status == "scheduled"
        assert p.scheduled_for is not None


def test_individual_approval_without_schedule_raises_error_when_no_slots(env, monkeypatch):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "test"}, media_type="carousel",
                                image_urls=["https://cdn.test/1.jpg"])
        pub_id = pub.id
    # Monkeypatch target schedule returning None
    monkeypatch.setattr("src.automation_api._schedule_target", lambda session, pub: None)
    with pytest.raises(HTTPException) as exc:
        automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest(publish_now=False, scheduled_for=None))
    assert exc.value.status_code == 400
    assert "Jadwal publikasi tidak dapat ditentukan" in exc.value.detail


def test_autopilot_mode_auto_schedules_after_successful_qc(env):
    from src.core import scheduler
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        item = ContentStrategyItem(plan_date="2026-11-10", topic="Konten Autopilot QC", format="carousel",
                                   content_pillar="Tips Praktis", objective="Edukasi", target_segment="Umum",
                                   scheduled_slot="09:00 WIB", status="producing", run_id=run_id)
        s.add(item)
        run = s.get(Run, run_id)
        run.status = "ok"
        auto_set = automation.get_settings(s, create=True)
        auto_set.publishing_mode = "autopilot"
        auto_set.require_approval = False
        s.commit()

    # Jalankan sync_and_automate
    scheduler.sync_and_automate(factory)

    with factory() as s:
        pub = ps.get_for_run(s, run_id)
        assert pub is not None
        assert pub.status == "scheduled"
        assert pub.scheduled_for is not None
        cal = s.scalars(select(ContentStrategyItem).where(ContentStrategyItem.run_id == run_id)).first()
        assert cal.status == "scheduled"


def test_review_mode_retains_review_queue(env):
    from src.core import scheduler
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        item = ContentStrategyItem(plan_date="2026-11-10", topic="Konten Review Mode", format="carousel",
                                   content_pillar="Tips Praktis", objective="Edukasi", target_segment="Umum",
                                   scheduled_slot="09:00 WIB", status="producing", run_id=run_id)
        s.add(item)
        run = s.get(Run, run_id)
        run.status = "ok"
        auto_set = automation.get_settings(s, create=True)
        auto_set.publishing_mode = "review"
        auto_set.require_approval = True
        s.commit()

    # Jalankan sync_and_automate
    scheduler.sync_and_automate(factory)

    with factory() as s:
        pub = ps.get_for_run(s, run_id)
        # Di review mode, publication belum otomatis dijadwalkan
        assert pub is None or pub.status == "pending_approval"


def test_scheduler_ignores_null_or_future_scheduled_for(env, monkeypatch):
    from src.core import scheduler
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    now = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
    with factory() as s:
        # Pub 1: scheduled_for is None
        p1 = Publication(run_id=run_id, status="scheduled", platform="instagram",
                         caption="c", image_urls_json="[]", approved_at=now, scheduled_for=None)
        # Pub 2: scheduled_for is in future
        p2 = Publication(run_id="run-future", status="scheduled", platform="instagram",
                         caption="c", image_urls_json="[]", approved_at=now,
                         scheduled_for=now + timedelta(hours=2))
        # Pub 3: scheduled_for is due
        p3 = Publication(run_id="run-due", status="scheduled", platform="instagram",
                         caption="c", image_urls_json="[]", approved_at=now,
                         scheduled_for=now - timedelta(minutes=5))
        s.add_all([p1, p2, p3])
        s.commit()

    published_runs = []
    monkeypatch.setattr("src.agents.publisher.execute_publication", lambda pid, **k: published_runs.append(pid))
    res = scheduler.run_once(factory, publish_fn=lambda r: None, now=now)
    # Only p3 should be published
    assert len(published_runs) == 1
    with factory() as s:
        p3_loaded = s.scalars(select(Publication).where(Publication.run_id == "run-due")).first()
        assert published_runs[0] == p3_loaded.id


def test_automation_pause_prevents_publication(env, monkeypatch):
    from src.core import scheduler
    factory, run_id, out_dir = env
    now = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
    with factory() as s:
        p = Publication(run_id=run_id, status="scheduled", platform="instagram",
                        caption="c", image_urls_json="[]", approved_at=now,
                        scheduled_for=now - timedelta(minutes=5))
        s.add(p)
        auto_set = automation.get_settings(s, create=True)
        auto_set.enabled = False
        auto_set.state = "paused"
        s.commit()

    published = []
    monkeypatch.setattr("src.agents.publisher.execute_publication", lambda pid, **k: published.append(pid))
    res = scheduler.run_once(factory, publish_fn=lambda r: None, now=now)
    assert res == []
    assert published == []


def test_duplicate_scheduling_prevention(env):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "test"}, media_type="carousel",
                                image_urls=["https://cdn.test/1.jpg"])
        pub_id = pub.id
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    # Panggil approve pertama kali
    res1 = automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest(publish_now=False, scheduled_for=future))
    assert res1["ok"] is True
    assert res1["status"] == "scheduled"
    # Panggil approve kedua kali (idempoten, tidak menduplikasi publikasi)
    res2 = automation_api.approve_publication(pub_id, request=_req(), req=automation_api.ApproveRequest(publish_now=False, scheduled_for=future))
    assert res2["ok"] is True
    assert res2["status"] == "scheduled"
    with factory() as s:
        all_pubs = s.scalars(select(Publication).where(Publication.run_id == run_id)).all()
        assert len(all_pubs) == 1


def test_successful_publication_triggers_analytics_eligibility(env):
    factory, run_id, out_dir = env
    _carousel_run(factory, run_id, out_dir)
    with factory() as s:
        pub = ps.ensure_pending(s, run_id=run_id, plan={"caption": "test"}, media_type="carousel",
                                image_urls=["https://cdn.test/1.jpg"])
        ps.mark_published(s, pub, media_id="IG_TEST_12345", permalink="https://instagram.com/p/12345")
        ps.ensure_analytics_row(s, pub, topic="Test Analytics", content_pillar="Tips", fmt="carousel")

    listed = automation_api.analytics_publications()
    found = [p for p in listed["items"] if p["media_id"] == "IG_TEST_12345"]
    assert len(found) == 1
    assert found[0]["publication_id"] == pub.id


def test_analytics_ingestion_handles_missing_credentials_and_errors(env, monkeypatch):
    monkeypatch.setattr("src.config.opt", lambda k, default=None: "" if k in ("IG_USER_ID", "IG_TOKEN") else default)
    with pytest.raises(HTTPException) as exc:
        automation_api.ingest_metrics()
    assert exc.value.status_code == 409
    assert "Instagram belum terhubung" in exc.value.detail

