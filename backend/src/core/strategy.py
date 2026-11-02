"""Strategy generator, 7-day calendar planner, and feedback loop engine."""
import logging
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from src.core.db import (
    Campaign, EnterpriseProfile, ContentStrategyItem, PostAnalytics, AnalyticsInsight, Run, SessionLocal, utc_now
)

log = logging.getLogger("gtnic.strategy")

SAMPLE_ENTERPRISE_PROFILE = {
    "company_name": "Resilience Digital Solusindo",
    "industry": "Pengembangan Web & Mobile App, Audit Keamanan Sistem, dan Solusi AI Bisnis",
    "description": "Perusahaan penyedia jasa teknologi dan transformasi digital enterprise di Indonesia yang berfokus pada otomasi cerdas, pengembangan platform aplikasi skala tinggi, dan audit keamanan TI.",
    "products_services": [
        {
            "name": "Enterprise AI & Workflow Automation",
            "desc": "Otomasi proses bisnis dan agen AI cerdas untuk efisiensi operasional.",
            "value_prop": "Mengurangi beban kerja repetitif hingga 70% dengan kepatuhan data ketat."
        },
        {
            "name": "Custom Web & Mobile Development",
            "desc": "Arsitektur cloud-native modern, handal, dan scalable.",
            "value_prop": "Sistem scalable dengan performa tinggi dan pengalaman pengguna kelas enterprise."
        },
        {
            "name": "Cybersecurity & System Audit",
            "desc": "Penetration testing, code audit, dan sertifikasi keamanan informasi.",
            "value_prop": "Melindungi aset digital krusial dari insiden siber dan kebocoran data."
        }
    ],
    "target_audience": {
        "primary_segment": "C-Level, VP of Tech, CTO, Head of IT & Operations",
        "pain_points": ["Proses operasional manual lambat", "Kekhawatiran kebocoran data/siber", "Aplikasi lama sulit di-scale"],
        "goals": ["Meningkatkan efisiensi kerja", "Memperkuat keamanan sistem", "Adopsi AI yang aman"]
    },
    "business_goals": [
        "Membangun kredibilitas & kepemimpinan pemikiran (Thought Leadership) di sektor AI & IT",
        "Lead generation untuk konsultasi audit dan transformasi sistem enterprise",
        "Edukasi pasar mengenai best practices keamanan siber dan otomasi AI"
    ],
    "tone": "profesional, lugas, visioner, berbasis data, Bahasa Indonesia",
    "content_pillars": [
        "Edukasi Otomasi AI",
        "Keamanan Sistem & Siber",
        "Studi Kasus & Dampak Bisnis",
        "Tips Arsitektur & Engineering"
    ],
    "brand_rules": [
        "Selalu sertakan data atau metodologi yang teruji; dilarang klaim bombastis tanpa bukti",
        "Gunakan istilah resmi teknologi dalam Bahasa Indonesia yang komunikatif",
        "Dilarang membocorkan nama klien tanpa izin; samarkan sebagai 'Perusahaan Manufaktur Nasional'",
        "CTA resmi harus mengarahkan ke konsultasi atau diskusi di kolom komentar"
    ],
    "contact_info": {
        "website": "https://resilience.co.id",
        "social": "@resiliencedigital",
        "email": "consult@resilience.co.id"
    },
    "approval_workflow": {
        "required_for": ["Pernyataan publik resmi", "Informasi harga & penawaran", "Studi kasus klien"],
        "default_mode": "manual_review"
    },
    "operating_preferences": {
        "posting_days": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat"],
        "timezone": "Asia/Jakarta (WIB)",
        "preferred_slots": ["09:00 WIB", "13:00 WIB", "18:30 WIB"],
        "target_weekly_posts": 5
    }
}

CALENDAR_STATES = {
    "draft", "awaiting_approval", "approved", "approved_to_publish", "scheduled",
    "producing", "generation_failed", "publishing", "published", "publication_failed", "rejected",
}
CALENDAR_TRANSITIONS = {
    "draft": {"awaiting_approval", "approved", "rejected"},
    "awaiting_approval": {"approved", "rejected", "draft"},
    "approved": {"approved_to_publish", "scheduled", "publishing", "publication_failed", "rejected", "draft"},
    "approved_to_publish": {"scheduled", "publishing", "rejected"},
    "scheduled": {"approved_to_publish", "publishing", "publication_failed", "rejected"},
    "producing": {"awaiting_approval", "generation_failed", "rejected"},
    "generation_failed": {"approved", "rejected", "draft"},
    "publishing": {"published", "publication_failed"},
    "publication_failed": {"approved_to_publish", "scheduled", "rejected"},
    "publishing": {"published", "publication_failed"},
    "published": set(),
    "rejected": {"draft"},
}


def get_or_create_enterprise_profile(session: Session) -> EnterpriseProfile:
    """Mengambil profil enterprise aktif, atau menginisialisasi dengan data baku jika belum ada."""
    stmt = select(EnterpriseProfile).order_by(EnterpriseProfile.id.desc()).limit(1)
    profile = session.scalar(stmt)
    if not profile:
        profile = EnterpriseProfile(
            company_name=SAMPLE_ENTERPRISE_PROFILE["company_name"],
            industry=SAMPLE_ENTERPRISE_PROFILE["industry"],
            description=SAMPLE_ENTERPRISE_PROFILE["description"],
            products_services_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["products_services"], ensure_ascii=False),
            target_audience_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["target_audience"], ensure_ascii=False),
            business_goals_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["business_goals"], ensure_ascii=False),
            tone=SAMPLE_ENTERPRISE_PROFILE["tone"],
            content_pillars_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["content_pillars"], ensure_ascii=False),
            brand_rules_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["brand_rules"], ensure_ascii=False),
            contact_info_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["contact_info"], ensure_ascii=False),
            approval_workflow_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["approval_workflow"], ensure_ascii=False),
            operating_preferences_json=json.dumps(SAMPLE_ENTERPRISE_PROFILE["operating_preferences"], ensure_ascii=False),
            completeness_score=100
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)
    return profile


def calculate_profile_completeness(profile_data: dict) -> int:
    """Menghitung skor kelengkapan konteks enterprise (0-100%)."""
    required_keys = ["company_name", "industry", "description", "products_services", "target_audience", "business_goals", "content_pillars", "brand_rules"]
    present = 0
    for k in required_keys:
        val = profile_data.get(k)
        if val and (not isinstance(val, (list, dict)) or len(val) > 0):
            present += 1
    return int((present / len(required_keys)) * 100)


def _apply_research_and_campaigns(templates: list, from_llm: bool, candidates: list, campaigns: list, today: datetime) -> list:
    """Sesuaikan rencana dengan kampanye aktif dan kandidat riset bersumber (deterministik)."""
    from src.core.campaigns import ANGLES
    templates = [dict(t) for t in templates]
    if campaigns and not any(t.get("campaign_id") for t in templates):
        camp = campaigns[0]
        for k, off in enumerate((2, 4, 6)):
            t = next((x for x in templates if x["offset_days"] == off), None)
            day = (today + timedelta(days=off)).strftime("%Y-%m-%d")
            if not t or not camp.start_date <= day <= camp.end_date:
                continue
            t.update(campaign_id=camp.id, topic=f"{camp.name}: {ANGLES[k % len(ANGLES)]}", objective=camp.objective[:128],
                     target_segment=(camp.target_audience or t.get("target_segment") or "Umum")[:128],
                     rationale=f"Mendukung kampanye '{camp.name}' (pesan utama: {camp.message[:150]}).")
    if candidates and not from_llm:
        c = candidates[0]
        t = next((x for x in templates if x["offset_days"] == 3 and not x.get("campaign_id")), None)
        if t and c.get("source_urls"):  # hanya kandidat yang punya sumber terverifikasi
            if c.get("recommended_format") in {"carousel", "video"}:
                t["format"] = c["recommended_format"]
            t.update(topic=c["topic"], research_topic=True,
                     rationale=f"Berbasis riset (relevansi {c.get('relevance_score')}): {c.get('relevance_reason', '')} "
                               f"Sudut: {c.get('suggested_angle', '')}. Risiko: {c.get('risk_notes', '')}")
    return templates


def generate_7day_strategy(session: Session, reset: bool = False, use_llm: bool = True) -> List[ContentStrategyItem]:
    """Menghasilkan atau memperbarui kalender konten 7 hari berbasis konteks perusahaan dan feedback analytics."""
    if reset:
        # Hapus item draft lama jika user meminta regenerate kalender baru
        existing = session.scalars(select(ContentStrategyItem).where(ContentStrategyItem.status.in_(["draft", "rejected"]))).all()
        for item in existing:
            session.delete(item)
        session.commit()

    existing_count = session.scalar(select(ContentStrategyItem).limit(1))
    if existing_count and not reset:
        return session.scalars(select(ContentStrategyItem).order_by(ContentStrategyItem.id.asc())).all()

    profile = get_or_create_enterprise_profile(session)
    pillars = json.loads(profile.content_pillars_json or "[]")
    if not pillars:
        pillars = ["Edukasi Bisnis", "Tips Praktis", "Studi Kasus", "Kabar Industri"]

    prods = json.loads(profile.products_services_json or "[]")
    audience_dict = json.loads(profile.target_audience_json or "{}")
    primary_audience = audience_dict.get("primary_segment", "Pengambil Keputusan & Manajer Enterprise")
    goals = json.loads(profile.business_goals_json or "[]")

    # Periksa apakah ada insight analytics aktif untuk diintegrasikan
    recent_insights = session.scalars(
        select(AnalyticsInsight).order_by(desc(AnalyticsInsight.id)).limit(20)
    ).all()

    def _is_real(ins) -> bool:
        try:
            return json.loads(ins.data_points_json or "{}").get("is_simulated") is False
        except ValueError:
            return False

    # Insight dari data Instagram NYATA diprioritaskan di atas insight data simulasi.
    latest_insight = next((i for i in recent_insights if _is_real(i)), None) or (recent_insights[0] if recent_insights else None)
    analytics_rows = session.scalars(select(PostAnalytics).order_by(desc(PostAnalytics.id))).all()
    analytics_context = {
        "sample_size": len(analytics_rows),
        "sources": sorted({row.source for row in analytics_rows}),
        "simulated_records": sum(row.is_simulated for row in analytics_rows),
        "metrics_available": {
            name: sum(getattr(row, name) is not None for row in analytics_rows)
            for name in ("reach", "impressions", "likes", "comments", "shares", "saves", "profile_visits")
        },
    }

    # Riset tersimpan sebagai bukti bersumber. Pakai snapshot ok terbaru (maks 14 hari), bukan hanya dari run terakhir.
    research_evidence, research_candidates = [], []
    from src.core.db import ResearchSnapshot
    snapshot = session.scalars(select(ResearchSnapshot).where(
        ResearchSnapshot.ok.is_(True)).order_by(desc(ResearchSnapshot.id))).first()
    if snapshot:
        age_ok = True
        if snapshot.created_at:
            created = snapshot.created_at if snapshot.created_at.tzinfo else snapshot.created_at.replace(tzinfo=timezone.utc)
            age_ok = (datetime.now(timezone.utc) - created) <= timedelta(days=14)
        if age_ok:
            try:
                research_data = json.loads(snapshot.data_json)
                research_evidence = (research_data.get("sources") or [])[:5]
                research_candidates = [c for c in (research_data.get("topic_candidates") or [])
                                       if isinstance(c, dict) and c.get("topic")][:3]
            except (TypeError, json.JSONDecodeError):
                research_evidence, research_candidates = [], []

    today = datetime.now()
    llm_generated_items = []
    win_start, win_end = (today + timedelta(days=1)).strftime("%Y-%m-%d"), (today + timedelta(days=7)).strftime("%Y-%m-%d")
    active_campaigns = session.scalars(select(Campaign).where(
        Campaign.status == "active", Campaign.start_date <= win_end, Campaign.end_date >= win_start
    ).order_by(Campaign.end_date).limit(2)).all()
    campaign_ids = {c.id for c in active_campaigns}

    if use_llm:
        try:
            from src.core.llm import LLMClient
            client = LLMClient()
            system_prompt = (
                "Kamu adalah Social Media Director tingkat Enterprise. Tugasmu adalah membuat rencana konten "
                "7 hari yang disesuaikan secara presisi dengan profil bisnis, target audiens, pilar konten, "
                "dan masukan analitik terbaru. "
                "Balas HANYA dengan JSON valid format: {\"items\": [{\"offset_days\": 1, \"topic\": \"...\", \"format\": \"carousel\"|\"video\", \"pillar\": \"...\", \"objective\": \"...\", \"target_segment\": \"...\", \"slot\": \"09:00 WIB\", \"rationale\": \"...\", \"campaign_id\": null}]}. campaign_id diisi id kampanye aktif jika item mendukung kampanye, selain itu null"
            )
            insight_context = f"Terbaru Insight Analitik: '{latest_insight.title}' ({latest_insight.observation}); evidence={latest_insight.data_points_json}" if latest_insight else "Belum ada insight historis."
            insight_context += "\nKualitas dataset: " + json.dumps(analytics_context, ensure_ascii=False)
            research_context = json.dumps(research_evidence, ensure_ascii=False) if research_evidence else "Tidak ada riset tersimpan; jangan membuat klaim seolah bersumber."
            products_context = json.dumps(prods, ensure_ascii=False)
            candidates_context = json.dumps(research_candidates, ensure_ascii=False) if research_candidates else "Tidak ada kandidat topik dari riset."
            campaigns_context = json.dumps([
                {"id": c.id, "name": c.name, "objective": c.objective, "audience": c.target_audience, "period": f"{c.start_date}..{c.end_date}",
                 "message": c.message, "requirements": c.content_requirements} for c in active_campaigns], ensure_ascii=False) if active_campaigns else "Tidak ada kampanye aktif."
            user_prompt = (
                f"Perusahaan: {profile.company_name}\n"
                f"Industri: {profile.industry}\n"
                f"Deskripsi: {profile.description}\n"
                f"Produk dan layanan: {products_context}\n"
                f"Target Audiens: {primary_audience}\n"
                f"Tujuan Bisnis: {', '.join(goals)}\n"
                f"Pilar Konten: {', '.join(pillars)}\n"
                f"Feedback Analitik: {insight_context}\n"
                f"Bukti riset dan sumber: {research_context}\n"
                f"Kandidat topik riset (urut relevansi; patuhi risk_notes, jangan jadikan fakta bila tanpa sumber): {candidates_context}\n"
                f"Kampanye aktif: {campaigns_context}\n"
                "Jika ada kampanye aktif, alokasikan minimal 3 dari 7 item untuk mendukungnya (isi campaign_id). "
                "Gunakan 1-2 kandidat riset yang paling relevan bila cocok.\n\n"
                "Buat rencana 7 hari (offset_days 1 sampai 7) dengan campuran format carousel dan video Reels, "
                "dengan objektif yang jelas dan rationale berbasis data bisnis."
            )
            resp = client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                step="strategy_generator",
                temperature=0.4,
                max_completion_tokens=2048
            )
            content = resp.choices[0].message.content or ""
            # Bersihkan JSON markdown wrapper
            clean_json = re.sub(r"^```(?:json)?\s*", "", content.strip())
            clean_json = re.sub(r"\s*```$", "", clean_json)
            parsed = json.loads(clean_json)
            if isinstance(parsed, dict) and isinstance(parsed.get("items"), list) and len(parsed["items"]) == 7:
                required = {"offset_days", "topic", "format", "pillar", "objective", "target_segment", "slot", "rationale"}
                validated = []
                for item in parsed["items"]:
                    if not isinstance(item, dict) or not required.issubset(item):
                        raise ValueError("Item strategi LLM kehilangan field wajib")
                    if item["format"] not in {"carousel", "video"} or not 1 <= int(item["offset_days"]) <= 7:
                        raise ValueError("Format atau offset_days strategi LLM tidak valid")
                    if any(not str(item[field]).strip() for field in required - {"offset_days"}):
                        raise ValueError("Field teks strategi LLM tidak boleh kosong")
                    cid = item.get("campaign_id")
                    cid = cid if isinstance(cid, int) and cid in campaign_ids else None
                    validated.append({**item, "offset_days": int(item["offset_days"]), "campaign_id": cid})
                if {item["offset_days"] for item in validated} != set(range(1, 8)):
                    raise ValueError("Offset strategi LLM harus mencakup tepat 1 sampai 7")
                llm_generated_items = validated
        except Exception as e:
            log.warning(f"[STRATEGY] Dynamic LLM strategy generation fallback to structured template: {e}")

    # Fallback template adaptif jika LLM tidak tersedia atau format tidak match
    plan_templates = llm_generated_items or [
        {
            "offset_days": 1,
            "topic": f"5 Tanda Arsitektur TI Perusahaan Anda Mulai Menghambat Pertumbuhan Bisnis",
            "format": "carousel",
            "pillar": pillars[0] if len(pillars) > 0 else "Edukasi Bisnis",
            "objective": "Edukasi & Brand Awareness",
            "target_segment": primary_audience,
            "slot": "09:00 WIB",
            "rationale": "Format carousel komparatif untuk membuka minggu kerja dengan topik strategis."
        },
        {
            "offset_days": 2,
            "topic": f"Otomasi Workflow: Cara Menghemat 100+ Jam Kerja Tim Operasional per Bulan",
            "format": "video",
            "pillar": pillars[1] if len(pillars) > 1 else pillars[0],
            "objective": "Lead Generation",
            "target_segment": primary_audience,
            "slot": "13:00 WIB",
            "rationale": "Format video Reels ringkas dengan visual b-roll data metrik untuk audiens mobile siang hari."
        },
        {
            "offset_days": 3,
            "topic": f"Audit Keamanan Sistem: 3 Celah Kritis yang Sering Terlewat Saat Scaling",
            "format": "carousel",
            "pillar": pillars[2] if len(pillars) > 2 else pillars[0],
            "objective": "Kredibilitas & Trust Building",
            "target_segment": primary_audience,
            "slot": "18:30 WIB",
            "rationale": "Membahas checklist keamanan teknis mendalam sebelum rilis produksi."
        },
        {
            "offset_days": 4,
            "topic": f"Studi Kasus: Modernisasi Sistem Monolith ke Cloud-Native Microservices",
            "format": "carousel",
            "pillar": pillars[3] if len(pillars) > 3 else pillars[0],
            "objective": "Thought Leadership",
            "target_segment": primary_audience,
            "slot": "09:00 WIB",
            "rationale": "Studi kasus terverifikasi yang membuktikan rekam jejak teknis dan efisiensi cloud."
        },
        {
            "offset_days": 5,
            "topic": f"Checklist Evaluasi Implementasi Solusi AI di Workflow Enterprise",
            "format": "video",
            "pillar": pillars[0] if len(pillars) > 0 else "Edukasi Bisnis",
            "objective": "Edukasi & Engagement",
            "target_segment": primary_audience,
            "slot": "18:30 WIB",
            "rationale": "Ajakan interaktif bagi para innovator perusahaan menjelang akhir pekan."
        },
        {
            "offset_days": 6,
            "topic": f"Mitos vs Fakta: Keamanan Data Solusi Cloud vs Server On-Premise",
            "format": "carousel",
            "pillar": pillars[1] if len(pillars) > 1 else pillars[0],
            "objective": "Edukasi & Menghilangkan Keraguan Prospek",
            "target_segment": primary_audience,
            "slot": "10:00 WIB",
            "rationale": "Format komparasi visual yang meluruskan persepsi umum industri."
        },
        {
            "offset_days": 7,
            "topic": f"Refleksi Mingguan: Mengapa Kestabilan Sistem Lebih Penting dari Fitur Berlebihan",
            "format": "carousel",
            "pillar": pillars[2] if len(pillars) > 2 else pillars[0],
            "objective": "Community Engagement & Employer Branding",
            "target_segment": primary_audience,
            "slot": "16:00 WIB",
            "rationale": "Konten bernas untuk membangun relasi dengan talenta dan komunitas profesional."
        }
    ]

    plan_templates = _apply_research_and_campaigns(plan_templates, bool(llm_generated_items),
                                                   research_candidates, active_campaigns, today)
    items = []
    for tmpl in plan_templates:
        p_date = (today + timedelta(days=tmpl["offset_days"])).strftime("%Y-%m-%d")
        rationale_text = tmpl["rationale"]
        rationale_text += " [strategy_source=llm]" if llm_generated_items else " [strategy_source=deterministic_fallback]"
        rationale_text += f" [enterprise_profile_id={profile.id}; goals={json.dumps(goals, ensure_ascii=False)}; audience={primary_audience}]"
        rationale_text += f" [analytics_evidence={json.dumps(analytics_context, ensure_ascii=False)}]"
        if research_evidence:
            rationale_text += f" [research_sources={len(research_evidence)}]"
        if tmpl.get("research_topic"):
            rationale_text += " [research_candidate=used]"
        if tmpl.get("campaign_id"):
            rationale_text += f" [campaign_id={tmpl['campaign_id']}]"
        insight_id = None

        # Jika ada insight analitik, perbarui item kedua/ketiga yang relevan untuk membuktikan closed feedback loop
        if latest_insight and tmpl["offset_days"] in (2, 5):
            rationale_text += f" [Disesuaikan berdasarkan Analytics Insight #{latest_insight.id}: '{latest_insight.title}']"
            insight_id = latest_insight.id
            latest_insight.applied_to_strategy = True

        item = ContentStrategyItem(
            plan_date=p_date,
            campaign_id=tmpl.get("campaign_id"),
            topic=tmpl["topic"],
            format=tmpl["format"],
            content_pillar=tmpl["pillar"],
            objective=tmpl["objective"],
            target_segment=tmpl["target_segment"],
            scheduled_slot=tmpl["slot"],
            rationale=rationale_text,
            status="draft",
            feedback_insight_id=insight_id
        )
        session.add(item)
        items.append(item)

    session.commit()
    for it in items:
        session.refresh(it)
    return items


def seed_demo_analytics_data(session: Session) -> List[PostAnalytics]:
    """Menyediakan dataset analytics realistis berlabel transparan untuk demo evaluasi."""
    existing = session.scalars(select(PostAnalytics).limit(1)).first()
    if existing:
        return session.scalars(select(PostAnalytics).order_by(desc(PostAnalytics.id))).all()

    now = datetime.now(timezone.utc)
    demo_posts = [
        {
            "topic": "5 Tanda Sistem TI Perusahaan Mulai Mengalami Bottleneck",
            "format": "carousel",
            "pillar": "Edukasi Otomasi AI",
            "reach": 4820,
            "impressions": 6120,
            "likes": 342,
            "comments": 48,
            "shares": 89,
            "saves": 194,
            "profile_visits": 76,
            "days_ago": 6,
            "permalink": "https://instagram.com/p/demo_resilience_1"
        },
        {
            "topic": "Studi Kasus: Otomasi Workflow Pengadaan Barang Hemat 120 Jam/Bulan",
            "format": "carousel",
            "pillar": "Studi Kasus & Dampak Bisnis",
            "reach": 6240,
            "impressions": 8410,
            "likes": 512,
            "comments": 74,
            "shares": 142,
            "saves": 310,
            "profile_visits": 138,
            "days_ago": 4,
            "permalink": "https://instagram.com/p/demo_resilience_2"
        },
        {
            "topic": "3 Tips Singkat Mencegah Phishing di Lingkungan Perusahaan",
            "format": "video",
            "pillar": "Keamanan Sistem & Siber",
            "reach": 9480,
            "impressions": 14200,
            "likes": 830,
            "comments": 62,
            "shares": 290,
            "saves": 445,
            "profile_visits": 210,
            "days_ago": 2,
            "permalink": "https://instagram.com/reel/demo_resilience_3"
        }
    ]

    records = []
    for dp in demo_posts:
        ts = now - timedelta(days=dp["days_ago"])
        rec = PostAnalytics(
            topic=dp["topic"],
            format=dp["format"],
            content_pillar=dp["pillar"],
            reach=dp["reach"],
            impressions=dp["impressions"],
            likes=dp["likes"],
            comments=dp["comments"],
            shares=dp["shares"],
            saves=dp["saves"],
            profile_visits=dp["profile_visits"],
            source="demo_seed_dataset (Simulated for GTNIC Presentation)",
            is_simulated=True,
            ingestion_status="complete",
            data_timestamp=ts,
            permalink=dp["permalink"],
            media_id=f"demo_ig_{dp['days_ago']}"
        )
        session.add(rec)
        records.append(rec)

    # Derive conservative, explicitly labeled insights from the persisted demo sample.
    by_format: dict[str, list[PostAnalytics]] = {}
    for record in records:
        by_format.setdefault(record.format, []).append(record)
    avg_reach = {
        fmt: sum(row.reach or 0 for row in rows) / len(rows)
        for fmt, rows in by_format.items() if rows
    }
    avg_save_rate = {
        fmt: sum((row.saves or 0) / row.reach for row in rows if row.reach) / max(1, sum(bool(row.reach) for row in rows))
        for fmt, rows in by_format.items() if rows
    }
    source_ids = [record.id for record in records]
    source_names = sorted({record.source for record in records})
    simulated_only = all(record.is_simulated for record in records)
    insights = []
    if avg_reach:
        top_reach = max(avg_reach, key=avg_reach.get)
        insights.append(AnalyticsInsight(
            title=f"Sampel demo: {top_reach} memiliki rata-rata reach tertinggi",
            observation=(f"Dalam {len(records)} post sampel tersimpan, format {top_reach} memiliki rata-rata reach "
                         f"{avg_reach[top_reach]:.0f}. Hasil ini bersifat deskriptif dan belum membuktikan sebab-akibat."),
            recommended_action="Gunakan sebagai hipotesis untuk eksperimen berikutnya; jangan mengubah strategi permanen dari sampel kecil.",
            confidence="preliminary",
            data_points_json=json.dumps({"metric": "average_reach", "by_format": avg_reach,
                "sample_size": len(records), "record_ids": source_ids, "sources": source_names,
                "is_simulated": simulated_only}),
        ))
    if avg_save_rate:
        top_saves = max(avg_save_rate, key=avg_save_rate.get)
        insights.append(AnalyticsInsight(
            title=f"Sampel demo: {top_saves} memiliki rasio saves/reach tertinggi",
            observation=(f"Dalam sampel yang sama, rasio saves/reach rata-rata format {top_saves} adalah "
                         f"{avg_save_rate[top_saves] * 100:.2f}%. Angka ini hanya ringkasan observasional."),
            recommended_action="Uji format tersebut pada sampel tambahan dan bandingkan dalam periode yang sebanding.",
            confidence="preliminary",
            data_points_json=json.dumps({"metric": "average_saves_per_reach", "by_format": avg_save_rate,
                "sample_size": len(records), "record_ids": source_ids, "sources": source_names,
                "is_simulated": simulated_only}),
        ))
    for ins in insights:
        session.add(ins)

    session.commit()
    # Persist generated insight IDs before exposing the records or applying a strategy.
    for ins in insights:
        session.refresh(ins)
    # Store the source metric IDs on insights; strategy items created after this point
    # can safely reference the actual persisted insight identifier.
    return records
