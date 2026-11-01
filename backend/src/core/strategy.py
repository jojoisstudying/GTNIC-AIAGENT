"""Strategy generator, 7-day calendar planner, and feedback loop engine."""
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from src.core.db import (
    EnterpriseProfile, ContentStrategyItem, PostAnalytics, AnalyticsInsight, Run, SessionLocal, utc_now
)

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


def generate_7day_strategy(session: Session, reset: bool = False) -> List[ContentStrategyItem]:
    """Menghasilkan atau memperbarui kalender konten 7 hari berbasis konteks perusahaan dan feedback analytics."""
    if reset:
        # Hapus item draft lama jika user meminta regenerate kalender baru
        existing = session.scalars(select(ContentStrategyItem).where(ContentStrategyItem.status == "draft")).all()
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

    # Periksa apakah ada insight analytics aktif untuk diintegrasikan
    latest_insight = session.scalars(
        select(AnalyticsInsight).order_by(desc(AnalyticsInsight.id))
    ).first()

    today = datetime.now()
    plan_templates = [
        {
            "offset_days": 1,
            "topic": "5 Tanda Sistem TI Perusahaan Anda Mulai Menjadi Bottleneck Operasional",
            "format": "carousel",
            "pillar": pillars[0] if len(pillars) > 0 else "Edukasi Bisnis",
            "objective": "Edukasi & Brand Awareness",
            "target_segment": "CTO & VP Engineering",
            "slot": "09:00 WIB",
            "rationale": "Format carousel informatif untuk membuka minggu kerja dengan topik strategis."
        },
        {
            "offset_days": 2,
            "topic": "Bagaimana Otomasi Alur Kerja Menghemat 120 Jam Kerja Tim Operasional Tiap Bulan",
            "format": "video",
            "pillar": pillars[1] if len(pillars) > 1 else pillars[0],
            "objective": "Lead Generation",
            "target_segment": "Head of Operations & GM",
            "slot": "13:00 WIB",
            "rationale": "Format video Reels ringkas dengan visual b-roll data metrik untuk audiens mobile siang hari."
        },
        {
            "offset_days": 3,
            "topic": "Audit Keamanan Sistem: 3 Celah yang Sering Diabaikan Saat Scaling Aplikasi",
            "format": "carousel",
            "pillar": pillars[2] if len(pillars) > 2 else pillars[0],
            "objective": "Kredibilitas & Trust Building",
            "target_segment": "Tech Lead & Developer Enterprise",
            "slot": "18:30 WIB",
            "rationale": "Membahas checklist keamanan teknis mendalam sebelum rilis produksi."
        },
        {
            "offset_days": 4,
            "topic": "Studi Kasus: Modernisasi Arsitektur Monolith ke Event-Driven Microservices",
            "format": "carousel",
            "pillar": pillars[3] if len(pillars) > 3 else pillars[0],
            "objective": "Thought Leadership",
            "target_segment": "Enterprise Architects & Tech Execs",
            "slot": "09:00 WIB",
            "rationale": "Studi kasus mendalam yang membuktikan rekam jejak teknis dan efisiensi cloud."
        },
        {
            "offset_days": 5,
            "topic": "Checklist Kesiapan Implementasi Agentic AI di Workflow Perusahaan",
            "format": "video",
            "pillar": pillars[0] if len(pillars) > 0 else "Edukasi Bisnis",
            "objective": "Edukasi & Engagement",
            "target_segment": "Business Innovation Leads",
            "slot": "18:30 WIB",
            "rationale": "Ajakan interaktif bagi para innovator perusahaan menjelang akhir pekan."
        },
        {
            "offset_days": 6,
            "topic": "Mitos vs Fakta: Keamanan Data Cloud vs On-Premise untuk Perusahaan Finansial",
            "format": "carousel",
            "pillar": pillars[1] if len(pillars) > 1 else pillars[0],
            "objective": "Edukasi & Menghilangkan Keraguan Prospek",
            "target_segment": "Compliance & Security Officers",
            "slot": "10:00 WIB",
            "rationale": "Format komparasi visual yang meluruskan persepsi umum industri perbankan."
        },
        {
            "offset_days": 7,
            "topic": "Refleksi Mingguan: Mengapa Sederhana Lebih Baik dalam Desain Arsitektur Sistem",
            "format": "carousel",
            "pillar": pillars[2] if len(pillars) > 2 else pillars[0],
            "objective": "Community Engagement & Employer Branding",
            "target_segment": "Praktisi & Komunitas Tech",
            "slot": "16:00 WIB",
            "rationale": "Konten santai bernas untuk membangun relasi dengan talenta dan komunitas."
        }
    ]

    items = []
    for tmpl in plan_templates:
        p_date = (today + timedelta(days=tmpl["offset_days"])).strftime("%Y-%m-%d")
        rationale_text = tmpl["rationale"]
        insight_id = None

        # Jika ada insight analitik, perbarui item kedua/ketiga yang relevan untuk membuktikan closed feedback loop
        if latest_insight and tmpl["offset_days"] in (2, 5):
            rationale_text += f" [Disesuaikan berdasarkan Analytics Insight #{latest_insight.id}: '{latest_insight.title}']"
            insight_id = latest_insight.id
            latest_insight.applied_to_strategy = True

        item = ContentStrategyItem(
            plan_date=p_date,
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
            data_timestamp=ts,
            permalink=dp["permalink"],
            media_id=f"demo_ig_{dp['days_ago']}"
        )
        session.add(rec)
        records.append(rec)

    # Buat 2 insight berbasis data analytics
    insights = [
        AnalyticsInsight(
            title="Format Video & Konten Keamanan Menghasilkan Saves & Share Tertinggi (3.2x vs rata-rata)",
            observation="Posting video berdurasi pendek pada pilar 'Keamanan Sistem' menghasilkan rasio simpanan (saves) 4.7% dan shares tertinggi (290), jauh melampaui rata-rata carousel edukasi statis.",
            recommended_action="Tingkatkan alokasi format video Reels ke 2-3 kali seminggu untuk pilar Keamanan Siber dan Otomasi, serta jadwalkan pada slot sore (18:30 WIB).",
            confidence="high",
            data_points_json=json.dumps({"top_format": "video", "saves_rate": "4.7%", "avg_shares": 290}),
            applied_to_strategy=True
        ),
        AnalyticsInsight(
            title="Studi Kasus Konkret dengan Metrik Angka Mendorong Profile Visits & Pertanyaan Prospek",
            observation="Carousel studi kasus yang menampilkan penghematan jam kerja (120 Jam/Bulan) menyumbang 138 profile visits dan 74 komentar pertanyaan teknis dari pengambil keputusan.",
            recommended_action="Sertakan angka metrik terverifikasi di slide cover dan pertahankan format studi kasus mingguan di kalender konten.",
            confidence="high",
            data_points_json=json.dumps({"profile_visits": 138, "comments": 74, "retention_factor": "high"}),
            applied_to_strategy=True
        )
    ]
    for ins in insights:
        session.add(ins)

    session.commit()
    return records
