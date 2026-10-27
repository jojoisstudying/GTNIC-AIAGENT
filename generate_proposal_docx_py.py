import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def create_element(name):
    return OxmlElement(name)

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def add_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 51, 102) # Deep Navy
    return p

def add_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 102, 153) # Slate Blue
    return p

def add_heading_3(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.italic = True
    run.font.color.rgb = RGBColor(51, 51, 51)
    return p

def add_body_paragraph(doc, text, bold_prefix=""):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.5
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = 'Times New Roman'
        r_pre.font.size = Pt(12)
        r_pre.font.bold = True
    r = p.add_run(text)
    r.font.name = 'Times New Roman'
    r.font.size = Pt(12)
    return p

def add_bullet_point(doc, text, bold_prefix="", level=0):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.left_indent = Inches(0.25 * (level + 1))
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = 'Times New Roman'
        r_pre.font.size = Pt(12)
        r_pre.font.bold = True
    r = p.add_run(text)
    r.font.name = 'Times New Roman'
    r.font.size = Pt(12)
    return p

def add_code_block(doc, text):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_background(cell, "F4F6F8")
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    # Border styling
    tcPr = cell._element.get_or_add_tcPr()
    tcBorders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="0" w:color="003366"/><w:top w:val="none"/><w:right w:val="none"/><w:bottom w:val="none"/></w:tcBorders>')
    tcPr.append(tcBorders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    run.font.name = 'Courier New'
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(33, 33, 33)

def build_proposal_document():
    doc = docx.Document()

    # Configure Margins (A4: Left 4 cm, Top 3 cm, Right 3 cm, Bottom 3 cm)
    for section in doc.sections:
        section.page_width = Inches(8.27)
        section.page_height = Inches(11.69)
        section.left_margin = Inches(1.57)   # ~4 cm
        section.top_margin = Inches(1.18)    # ~3 cm
        section.right_margin = Inches(1.18)  # ~3 cm
        section.bottom_margin = Inches(1.18) # ~3 cm

    # Set Default Style
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)
    font.color.rgb = RGBColor(0, 0, 0)

    # ---------------------------------------------------------
    # COVER PAGE
    # ---------------------------------------------------------
    p_logo = doc.add_paragraph()
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_logo = p_logo.add_run("[ LOGO GARDA TECH ]   |   [ LOGO GTNIC 2026 ]")
    r_logo.font.bold = True
    r_logo.font.size = Pt(10)
    r_logo.font.color.rgb = RGBColor(128, 128, 128)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(36)
    p_title.paragraph_format.space_after = Pt(12)
    r_title = p_title.add_run("PROPOSAL PROGRAM INOVASI\nGARDA TECH NATIONAL INNOVATION COMPETITION 2026")
    r_title.font.bold = True
    r_title.font.size = Pt(16)
    r_title.font.color.rgb = RGBColor(0, 51, 102)

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(36)
    r_sub = p_sub.add_run("KATEGORI: AI AGENTS\nSub-Tema: Building Intelligent AI Agents for Enterprise Productivity")
    r_sub.font.bold = True
    r_sub.font.size = Pt(12)
    r_sub.font.color.rgb = RGBColor(0, 102, 153)

    p_karya = doc.add_paragraph()
    p_karya.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_karya.paragraph_format.space_after = Pt(48)
    r_karya = p_karya.add_run("JUDUL KARYA:\nAUTO-CONTENT AGENT: Autonomous Multi-Agent Content Engineering & Publishing Orchestrator for Enterprise Social Media Dominance")
    r_karya.font.bold = True
    r_karya.font.size = Pt(13)

    p_team = doc.add_paragraph()
    p_team.paragraph_format.line_spacing = 1.3
    p_team.paragraph_format.space_after = Pt(36)
    
    details = [
        ("Nama Tim", ": [Nama Tim Anda]"),
        ("Institusi / Perguruan Tinggi", ": [Nama Universitas/Kampus/Sekolah]"),
        ("Ketua Tim", ": [Nama Lengkap Ketua / NIM / Email / No. HP]"),
        ("Anggota 1", ": [Nama Anggota 1 / NIM / Email]"),
        ("Anggota 2", ": [Nama Anggota 2 / NIM / Email]"),
        ("Tautan GitHub Repository", ": [Link GitHub Publik Repositori]"),
        ("Tautan Live Interface/Dashboard", ": [Link Live URL Deployment]"),
        ("Tautan Video Demo (3-5 Menit)", ": [Link YouTube / Google Drive Publik]")
    ]
    for label, val in details:
        p_t = doc.add_paragraph()
        p_t.paragraph_format.space_after = Pt(2)
        p_t.paragraph_format.line_spacing = 1.15
        r_lbl = p_t.add_run(f"{label:<30}")
        r_lbl.font.bold = True
        p_t.add_run(val)

    p_foot = doc.add_paragraph()
    p_foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_foot.paragraph_format.space_before = Pt(48)
    r_foot = p_foot.add_run("GARDA TECH NATIONAL INNOVATION COMPETITION (GTNIC)\n2026")
    r_foot.font.bold = True
    r_foot.font.size = Pt(11)

    doc.add_page_break()

    # ---------------------------------------------------------
    # DAFTAR ISI
    # ---------------------------------------------------------
    add_heading_1(doc, "DAFTAR ISI")
    toc_items = [
        "BAB 1: PENDAHULUAN & LATAR BELAKANG OPERASIONAL",
        "BAB 2: TUJUAN, MANFAAT, DAN TARGET PENGGUNA INDUSTRI",
        "BAB 3: ARSITEKTUR TEKNIS & REKAYASA SISTEM",
        "BAB 4: FITUR UTAMA & KAPABILITAS OTONOM AGEN",
        "BAB 5: BATASAN SISTEM, TATA KELOLA RISIKO, DAN KEAMANAN ENTERPRISE",
        "BAB 6: DESAIN ANTARMUKA DAN PENGALAMAN PENGGUNA (UX CASE STUDY)",
        "BAB 7: RENCANA PENGEMBANGAN LANJUTAN (FUTURE ROADMAP) & KESIMPULAN",
        "LAMPIRAN & DOKUMENTASI VALIDASI KARYA"
    ]
    for item in toc_items:
        p_toc = doc.add_paragraph()
        p_toc.paragraph_format.space_after = Pt(4)
        p_toc.paragraph_format.line_spacing = 1.3
        r_toc = p_toc.add_run(item)
        r_toc.font.bold = True

    doc.add_page_break()

    # ---------------------------------------------------------
    # BAB 1
    # ---------------------------------------------------------
    add_heading_1(doc, "BAB 1: PENDAHULUAN & LATAR BELAKANG OPERASIONAL")
    
    add_heading_2(doc, "1.1. Konteks Industri & Latar Belakang Masalah")
    add_body_paragraph(doc, "Dalam era transformasi digital modern, kehadiran media sosial korporat (seperti Instagram, LinkedIn, YouTube Shorts, dan TikTok) bukan lagi sekadar kanal pemasaran tambahan, melainkan aset digital strategis yang menentukan reputasi merek (brand authority), akuisisi pelanggan (lead generation), dan diferensiasi pasar bagi korporasi maupun pelaku usaha di Indonesia.")
    add_body_paragraph(doc, "Namun, di balik tuntutan omnipresence dan jadwal publikasi harian yang agresif, divisi pemasaran enterprise menghadapi hambatan operasional yang sangat berat (bottleneck):")
    add_bullet_point(doc, " Membutuhkan kolaborasi lintas fungsi yang mahal: Content Strategist/Researcher, Copywriter, Graphic Designer, Creative Director/QC, dan Social Media Specialist.", "1. Intensitas Sumber Daya & Biaya Tinggi:")
    add_bullet_point(doc, " Rata-rata waktu yang dihabiskan untuk menyelesaikan 1 konten komprehensif mulai dari riset data, drafting copy, revisi desain, hingga persetujuan manajerial memakan waktu 4 hingga 8 jam kerja.", "2. Siklus Produksi yang Lambat:")
    add_bullet_point(doc, " Kesalahan faktual, inkonsistensi palet warna/font pedoman merek (brand guidelines), teks terpotong (layout overflow), serta tata letak amatir sering lolos ke ranah publik akibat kelelahan tim (human fatigue).", "3. Ketidakkonsistenan Kualitas:")

    add_heading_2(doc, "1.2. Root Cause Analysis: Dilema Konten Enterprise (The Cost-Quality Paradox)")
    add_body_paragraph(doc, "Enterprise di Indonesia saat ini terjepit di antara dua pilihan yang sama-sama merugikan:")
    add_bullet_point(doc, " Menghasilkan konten berkualitas tinggi, tetapi menuntut anggaran operasional bulanan puluhan juta rupiah, koordinasi birokratis yang lambat, dan tidak fleksibel terhadap tren yang cepat berubah.", "Opsi A (Agensi Tradisional / Tim In-House Besar):")
    add_bullet_point(doc, " Cepat dan murah, namun menghasilkan konten berkualitas rendah yang tidak memenuhi standar korporat.", "Opsi B (Alat AI Generatif Konvensional / Template Canva):")

    add_heading_2(doc, "1.3. The Anti-AI-Slop Manifesto: Mengapa AI Konvensional Gagal di Level Enterprise?")
    add_body_paragraph(doc, "Adopsi AI generatif generik (seperti ChatGPT mentah atau Canva Magic Studio) justru menimbulkan masalah baru yang dikenal industri sebagai 'AI Slop':")
    add_bullet_point(doc, " LLM tanpa verifikasi kerap mengarang statistik dan data palsu yang fatal bagi reputasi korporat.", "• Halusinasi Faktual:")
    add_bullet_point(doc, " Model text-to-image generatif (seperti Midjourney atau Stable Diffusion mentah) menghasilkan tipografi berantakan, teks salah eja (gibberish text), dan tata letak acak yang tidak mematuhi standar desain editorial enterprise.", "• Desain Terdistorsi:")
    add_bullet_point(doc, " Narasi yang dihasilkan monoton, dipenuhi kata sifat hiperbolis kosong, dan tidak relevan dengan psikologi audiens profesional di Indonesia.", "• Teks Robotik & Klise:")

    add_heading_2(doc, "1.4. Identifikasi Masalah Utama")
    add_body_paragraph(doc, "Berdasarkan analisis di atas, rumusan masalah operasional yang dipecahkan dalam inovasi ini adalah:")
    add_bullet_point(doc, "Bagaimana merancang sistem AI Agent yang otonom, mampu melakukan riset fakta tervalidasi secara mandiri tanpa halusinasi, dan menyusun strategi narasi editorial korporat yang berbobot?")
    add_bullet_point(doc, "Bagaimana menggantikan generator visual acak dengan arsitektur rendering berbasis web (HTML/CSS + Headless Chrome) yang menjamin ketepatan tipografi piksel-sempurna (pixel-perfect) dan 100% kepatuhan brand guidelines?")
    add_bullet_point(doc, "Bagaimana mengimplementasikan multi-agent pipeline yang dilengkapi automated guardrails (inspeksi DOM, deteksi overflow, anti-repetition memory) dan mekanisme self-healing ketika terjadi deviasi konten?")
    add_bullet_point(doc, "Bagaimana menyediakan ekosistem end-to-end yang aman bagi enterprise, mencakup tracking biaya token transparan, proteksi aset figur korporat, hingga publikasi langsung ke Meta Graph API secara idempotent?")

    # ---------------------------------------------------------
    # BAB 2
    # ---------------------------------------------------------
    add_heading_1(doc, "BAB 2: TUJUAN, MANFAAT, DAN TARGET PENGGUNA INDUSTRI")
    
    add_heading_2(doc, "2.1. Tujuan Pengembangan Sistem")
    add_bullet_point(doc, "Membangun platform AI Social Media Content Engineering berbasis multi-agent yang mampu mengubah satu topik mentah menjadi draf carousel lengkap, divalidasi mutunya, dirender menjadi visual resolusi tinggi (1080x1350), dan dipublikasikan tanpa ketergantungan manual.")
    add_bullet_point(doc, "Mengeliminasi 100% risiko teks terpotong (text overflow) dan pelanggaran palet warna melalui Deterministic DOM Inspection.")
    add_bullet_point(doc, "Menyediakan visibilitas penuh (full auditability & observability) melalui event log terstruktur dan pelacakan anggaran (cost tracking per token) untuk tata kelola enterprise yang akuntabel.")

    add_heading_2(doc, "2.2. Nilai Tambah & Solusi Otomatisasi yang Ditawarkan")
    add_bullet_point(doc, " Memecah tugas kompleks menjadi sub-tugas yang dijalankan oleh agen khusus (Research, Planner, Designer, Publisher) dengan kontrak antarmuka yang ketat menggunakan Pydantic v2.", "Orkestrasi Multi-Agent Terspesialisasi:")
    add_bullet_point(doc, " Memadukan penelusuran web langsung (live search verification) dengan memori anti-pengulangan hook, variasi layout cerdas, dan tipografi modern ala editorial papan atas.", "Zero-AI-Slop Architecture:")
    add_bullet_point(doc, " Jika draf teks melebihi kapasitas visual atau melanggar aturan redaksional, agen pemeriksa (QC Guardrail) secara otomatis menolak dan memicu perbaikan balik ke agen perencana sebelum render visual dilanjutkan.", "Automated Quality Control & Self-Healing:")
    add_bullet_point(doc, " Idempotensi publikasi berbasis database status untuk mencegah posting ganda, dilengkapi monitoring status kedaluwarsa token dan peringatan proaktif (alerting).", "Enterprise-Grade Safe Publishing:")

    add_heading_2(doc, "2.3. Target Perusahaan dan Pengguna Industri (ICP)")
    add_bullet_point(doc, " Membutuhkan edukasi pasar harian seputar regulasi, investasi, dan teknologi dengan akurasi fakta mutlak.", "1. Perusahaan Finansial, SaaS, & FinTech:")
    add_bullet_point(doc, " Mengandalkan thought leadership di media sosial untuk membangun kredibilitas dan memikat klien tier-1.", "2. Korporasi Konsultan & B2B Services:")
    add_bullet_point(doc, " Membutuhkan sistem automasi skala besar (white-label) untuk menangani puluhan akun brand korporat dengan efisiensi tinggi.", "3. Agensi Pemasaran Digital & Media Rumah Kreatif:")
    add_bullet_point(doc, " Memerlukan konsistensi publikasi produk harian dengan aset talent resmi yang berlisensi.", "4. Perusahaan FMCG & Retail:")

    add_heading_2(doc, "2.4. Metrik Kuantitatif Efisiensi Operasional & Analisis ROI Bisnis")
    
    # Table Creation
    table = doc.add_table(rows=6, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Parameter Evaluasi", "Proses Manual Tradisional", "Solusi Auto-Content AI Agent", "Efisiensi / Peningkatan"]
    
    # Header Styling
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_background(hdr_cells[i], "003366")
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.size = Pt(10)

    rows_data = [
        ("Waktu Siklus Produksi (Lead Time)", "4 – 8 Jam per Konten Carousel", "1.5 – 3 Menit per Konten", "98.7% Penghematan Waktu"),
        ("Biaya Tenaga Kerja Operasional", "Rp 4.000.000 – Rp 8.000.000 / bln", "< Rp 50.000 / bln (Biaya Token)", "> 98% Reduksi Biaya"),
        ("Tingkat Kesalahan Desain & Overflow", "15% – 20% (Human Error)", "0% (Divalidasi via Playwright)", "Eliminasi 100% Cacat Visual"),
        ("Kapasitas Produksi Konten", "15 – 25 Konten / bulan / tim", "Ratusan Konten Terorkestransi", "Skalabilitas 10x - 20x"),
        ("Audit Kepatuhan Brand & Anggaran", "Sulit diukur & subjektif", "Audit Real-time per Run & Event Log", "100% Transparansi & Akuntabilitas")
    ]

    for r_idx, row in enumerate(rows_data):
        row_cells = table.rows[r_idx + 1].cells
        bg_color = "F9FAFB" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(row):
            row_cells[c_idx].text = val
            set_cell_background(row_cells[c_idx], bg_color)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=100, right=100)
            p = row_cells[c_idx].paragraphs[0]
            for run in p.runs:
                run.font.size = Pt(9.5)
                if c_idx == 3:
                    run.font.bold = True

    # ---------------------------------------------------------
    # BAB 3
    # ---------------------------------------------------------
    add_heading_1(doc, "BAB 3: ARSITEKTUR TEKNIS & REKAYASA SISTEM")
    
    add_heading_2(doc, "3.1. Filosofi Desain: Deterministic Layout Engines vs. Hallucinatory Generative Design")
    add_body_paragraph(doc, "Salah satu kelemahan terbesar sistem AI agent media sosial generasi pertama adalah mempercayakan pembuatan gambar teks kepada model difusi generatif. Hal tersebut menghasilkan tipografi rusak dan teks yang tidak bisa diedit.")
    add_body_paragraph(doc, "Proyek ini mengambil pendekatan teknik yang jauh lebih unggul: Deterministic HTML5/CSS3 Component Rendering. LLM bertindak sebagai Editor, Strategist, dan Information Architect, sementara visual dikomposisikan oleh mesin rendering modern (Chromium Headless via Playwright). Hal ini menjamin:")
    add_bullet_point(doc, "Ketajaman teks 100% pada resolusi 1080x1350 piksel (Rasio 4:5 standar Instagram).")
    add_bullet_point(doc, "Eksekusi layout CSS Flexbox dan Grid yang konsisten dengan pedoman brand korporat.")
    add_bullet_point(doc, "Kemampuan verifikasi DOM secara matematis sebelum file visual disimpan.")

    add_heading_2(doc, "3.2. Diagram Arsitektur Multi-Agent Komprehensif")
    add_body_paragraph(doc, "Berikut adalah gambaran alur logika sistem orkestrasi otonom:")
    
    arch_diagram_text = (
        "[ User / Dashboard ] -> [ FastAPI Gateway ] -> [ RunContext & SQLite ]\n"
        "       │\n"
        "       ├──> Stage 1: Research Agent (Tavily API Search -> Verified Research Snapshot)\n"
        "       ├──> Stage 2: Planner Agent (30 Templates Registry -> Pydantic Draft Plan -> QC Guardrail 1)\n"
        "       ├──> Stage 3: Designer Agent (Asset Vault -> Playwright Chrome -> DOM QC Guardrail 2 -> JPG Carousel)\n"
        "       └──> Stage 4: Publisher Agent (Cloudinary CDN -> Token Health Check -> Meta Graph API)\n"
        "       │\n"
        "[ EventEmitter ] -> [ SQLite Core Data Store ] -> [ Real-Time Dashboard Frontend ]"
    )
    add_code_block(doc, arch_diagram_text)

    add_heading_2(doc, "3.3. Spesifikasi Peran & Alur Logika Setiap Agent")
    add_heading_3(doc, "1. Research Agent (research_agent.py & facts.py)")
    add_body_paragraph(doc, "Menerima input topik dari pengguna, merumuskan kueri pencarian yang tajam, mengekstraksi data faktual, statistik kredibel, dan sumber terpercaya. Menganalisis ambiguitas kueri, melakukan triangulasi informasi dari multi-sumber Tavily, menyortir klaim yang belum terkonfirmasi, dan menyusun intisari fakta ke dalam skema Pydantic ResearchSnapshot.")

    add_heading_3(doc, "2. Planner Agent (planner.py)")
    add_body_paragraph(doc, "Bertindak sebagai Creative Director & Social Media Strategist. Mengubah fakta mentah menjadi alur cerita carousel yang memikat. Menghitung rasio kepadatan informasi (density budget) agar teks tidak berdesakan. Memilih template layout paling optimal dari Layout Registry (30 variasi layout teruji) dan menerapkan anti-repetition memory.")

    add_heading_3(doc, "3. Designer Agent (designer.py & render/)")
    add_body_paragraph(doc, "Mengonversi rancangan teks terstruktur dari Planner menjadi aset visual nyata beresolusi 1080x1350 piksel. Memilih cutout foto talent korporat beresolusi tinggi dari Asset Library yang memiliki lisensi dan persetujuan model. Membuka halaman HTML melalui Playwright Headless Chromium, melakukan simulasi render sub-piksel, dan mengeksekusi tangkapan layar kualitas tinggi.")

    add_heading_3(doc, "4. Publisher Agent (publisher.py)")
    add_body_paragraph(doc, "Bertanggung jawab atas distribusi aset ke platform target (Instagram Graph API). Melakukan validasi awal status token dan sisa kuota publikasi. Mengunggah slide visual ke CDN Cloudinary untuk memperoleh URL publik terenkripsi SSL, lalu mengeksekusi penerbitan secara idempotent.")

    add_heading_2(doc, "3.4. Action Execution & Tool Integrations")
    add_bullet_point(doc, " Penelusuran data web berbasis relevance scoring untuk data terkini.", "• Tavily AI Search Engine:")
    add_bullet_point(doc, " Mesin simulasi peramban untuk verifikasi DOM dan rendering visual.", "• Playwright Headless Chromium Engine:")
    add_bullet_point(doc, " Pustaka aset gambar dan b-roll video berlisensi komersial aman.", "• Pexels & Cutout Asset API:")
    add_bullet_point(doc, " CDN berkecepatan tinggi untuk manajemen aset publik berjangka waktu.", "• Cloudinary Media Hosting:")
    add_bullet_point(doc, " Titik integrasi resmi untuk penerbitan carousel dan monitoring performa metrik.", "• Meta Instagram Graph API:")

    add_heading_2(doc, "3.5. Technology Stack Matrix")
    add_bullet_point(doc, " Python 3.11 / 3.12 (Core Logic), FastAPI (ASGI Server).", "Backend & Gateway:")
    add_bullet_point(doc, " Groq Llama-3-70B / 8B (Inference berkecepatan tinggi >300 token/dtk).", "AI LLM Inference:")
    add_bullet_point(doc, " Pydantic v2 (Strict Data Typing & Validation).", "Data Validation:")
    add_bullet_point(doc, " Playwright + Jinja2 + CSS3 Flexbox/Grid.", "Visual Rendering Engine:")
    add_bullet_point(doc, " SQLite + SQLAlchemy 2.0 + Alembic (ACID Compliant).", "Database & Persistence:")
    add_bullet_point(doc, " Next.js / Tailwind CSS / React.", "Frontend Dashboard:")

    # ---------------------------------------------------------
    # BAB 4
    # ---------------------------------------------------------
    add_heading_1(doc, "BAB 4: FITUR UTAMA & KAPABILITAS OTONOM AGEN")
    add_heading_2(doc, "4.1. End-to-End Autonomous Pipeline")
    add_body_paragraph(doc, "Sistem memiliki kemampuan eksekusi otonom penuh dari titik awal (input topik kasar dari pengguna atau pembacaan jadwal konten otomatis) hingga status terpublikasi di media sosial tanpa bantuan manual di setiap langkah.")

    add_heading_2(doc, "4.2. DOM Headless Chrome Rendering & Subpixel Layout Verification")
    add_body_paragraph(doc, "Playwright mengevaluasi hierarki DOM secara langsung untuk memastikan tidak ada teks yang saling bertumpuk, kontainer meluap, atau ikon terpotong dengan tingkat kepresisian piksel sempurna.")

    add_heading_2(doc, "4.3. Automated Multi-Stage Guardrail & Self-Healing Loop")
    add_body_paragraph(doc, "Jika script qc_dom.py mendeteksi kondisi scrollHeight > clientHeight (teks meluap), sistem secara otomatis menolak desain tersebut, menyusun umpan balik kesalahan secara terstruktur, dan memerintahkan Planner Agent untuk memadatkan teks (self-correction loop).")

    add_heading_2(doc, "4.4. Enterprise Asset Vault & Licensed Talent Photo Protection")
    add_body_paragraph(doc, "Setiap foto talent memiliki metadata izin tertulis (consent check), tag ekspresi, dan hash SHA-256. Sistem melarang publikasi konten yang memuat foto placeholder generik.")

    # ---------------------------------------------------------
    # BAB 5
    # ---------------------------------------------------------
    add_heading_1(doc, "BAB 5: BATASAN SISTEM, TATA KELOLA RISIKO, DAN KEAMANAN ENTERPRISE")
    add_heading_2(doc, "5.1. Mitigasi Halusinasi Data & Pemalsuan Fakta")
    add_body_paragraph(doc, "Model bahasa diwajibkan menyertakan referensi sumber data pada setiap poin fakta yang diangkat. Angka dan statistik diekstraksi ke dalam slot data khusus tanpa diizinkan untuk diinterpretasi ulang secara bebas oleh LLM.")

    add_heading_2(doc, "5.2. Keamanan Kredensial & Redaksi Rahasia")
    add_body_paragraph(doc, "Fungsi core/http.py menerapkan sensor otomatis terhadap header otorisasi, parameter access_token, dan api_key sehingga tidak ada rahasia yang tercatat dalam log audit.")

    # ---------------------------------------------------------
    # BAB 6 & 7
    # ---------------------------------------------------------
    add_heading_1(doc, "BAB 6: DESAIN ANTARMUKA DAN PENGALAMAN PENGGUNA (UX CASE STUDY)")
    add_body_paragraph(doc, "Antarmuka pengguna dirancang dengan paradigma kesederhanaan maksimal (minimal effort, maximum control), dilengkapi Live Slide Preview dan Drawer Log Aktivitas Agen real-time.")

    wireframe_text = (
        "+---------------------------------------------------------------------------------------------------+\n"
        "|  AUTO-CONTENT AGENT | Enterprise Control Center                       [Brand: FinTech Solusi]     |\n"
        "+---------------------------------------------------------------------------------------------------+\n"
        "|  [+ Buat Konten Baru]  Topic: [ 5 Strategi Cashflow UKM Menghadapi Inflasi 2026           ]       |\n"
        "|                        Format: (o) Carousel Post IG   ( ) Short Video Reels   [ GENERATE ]        |\n"
        "+-------------------------------------------------+-------------------------------------------------+\n"
        "|  LIVE SLIDE PREVIEW (1080 x 1350)               |  AGENT THOUGHT PROCESS & EVENT OBSERVABILITY    |\n"
        "|  [ Slide 1/7 - 100% Pixel Perfect ]            |  [14:02:01] INFO  : Memulai Run Context         |\n"
        "|                                                 |  [14:02:05] AGENT1: Snapshot 4 fakta terkonfirmasi |\n"
        "|  5 STRATEGI KELOLA CASHFLOW USAHA DI 2026       |  [14:02:14] QC2   : DOM text overflow = 0 (Aman)|\n"
        "+-------------------------------------------------+-------------------------------------------------+\n"
        "|  ACTION BUTTONS: [ Edit Teks ]  [ Re-Generate ]  [ PUBLISH NOW TO INSTAGRAM ]                     |\n"
        "+---------------------------------------------------------------------------------------------------+"
    )
    add_code_block(doc, wireframe_text)

    add_heading_1(doc, "BAB 7: RENCANA PENGEMBANGAN LANJUTAN & KESIMPULAN")
    add_body_paragraph(doc, "Auto-Content Agent membuktikan bahwa implementasi AI di ranah enterprise tidak harus mengorbankan kualitas demi kecepatan. Dengan arsitektur otonom multi-agent yang memadukan penalaran LLM, riset tervalidasi, deterministic web layout engine, dan inspeksi visual ketat, sistem ini sukses menghilangkan AI-slop dan memberikan efisiensi operasional hingga 98% bagi perusahaan.")

    add_heading_1(doc, "LAMPIRAN & DOKUMENTASI VALIDASI KARYA")
    add_bullet_point(doc, " 116 dari 116 tests lulus (100% test coverage pada fungsi kritis agen, rendering, database, dan video pipeline).", "Hasil Unit Test Backend:")
    add_bullet_point(doc, " 30 variasi layout terdaftar dan tervalidasi siap pakai di src/layouts/.", "Katalog Template Layout:")
    add_bullet_point(doc, " Terlampir sesuai format resmi panitia GTNIC 2026.", "Surat Pernyataan Keaslian Karya:")

    # Save output file
    output_filename = "GTNIC2026_AIAgent_NamaTim.docx"
    doc.save(output_filename)
    print(f"Document successfully created and saved as: {output_filename}")

if __name__ == "__main__":
    build_proposal_document()