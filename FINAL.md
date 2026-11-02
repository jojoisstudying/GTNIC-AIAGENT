# GTNIC AI Agent — Complete Bug Fix & Reliability Plan

**Repository:** jojoisstudying/GTNIC-AIAGENT
**Branch:** main
**Baseline commit:** 6c1f687
**Audit date:** 2 November 2026
**Target:** Resolve all known bugs and verify the complete application before submission.

## Implementation evidence (2 November 2026)

Status is not marked FIXED unless the required regression tests pass. Local verification uses the user's existing `/home/ranggajm/.venvs/ai` environment; no packages were installed into a new environment.

- BUG-01: Structured semantic-QC result, blocking QC errors/exceptions, event/export/database traceability, topic/explicit brand-rule checks. Evidence: `tests/test_semantic_qc.py`, `tests/test_pipeline_context.py`.
- BUG-02: Publication-linked analytics FK, nullable unavailable metrics, pending ingestion state, upsert helper, publication/run/strategy linkage, duplicate guard, and observable persistence failures. Evidence: `tests/test_api_publish_reel.py`, `tests/test_publish_reel.py`, `tests/test_db_migration.py`.
- BUG-03: Fail-closed API key dependency, explicit development-only opt-in, production startup check, mutation-route dependencies and wildcard-CORS rejection. Evidence: `tests/test_auth_required.py`, `tests/test_upload_validation.py`.
- BUG-04: Chunk-bounded uploads, validate identifiers before filesystem operations, actual image decode/format verification, PNG normalization, pixel-count cap. Evidence: `tests/test_upload_validation.py`.
- BUG-05: Core requirements resolver dry-run passed with MoviePy 2.2.1 / Pillow 11.3.0. Security-patched rembg 2.0.82 requires Pillow >=12.1, so it is isolated in `requirements-image-processing.txt`; that resolver dry-run also passed. Added a one-shot worker selected by `REMBG_PYTHON`; the optional separate environment must still be configured and exercised on deployments that use cutout generation. Evidence: local dry-run results and `tests/test_pose_regenerate.py`.
- BUG-06: Enterprise fields flow into Planner and Reels prompts; immutable profile snapshots and run profile-version references added. Evidence: `tests/test_pipeline_context.py`, `tests/test_video_scriptwriter.py`.
- BUG-07: Strategy prompts include products/services, goals, saved research, analytics provenance; strict 7-day output validation and labeled deterministic fallback. Evidence: `tests/test_strategy_generation.py`.
- BUG-08: Simulated data visibly labeled; insights describe actual sample records with record IDs/sample size/source/limitations; metric ingestion upserts and leaves unknown values NULL. Evidence: `tests/test_enterprise_features.py`, `tests/test_api_publish_reel.py`.
- BUG-09: Approval and QC gates, state transition validation, duplicate publish prevention, publication failure states, actual published timestamp separate from proposed schedule. Evidence: `tests/test_api_publish_reel.py`, `tests/test_enterprise_features.py`, `tests/test_publish_reel.py`, `tests/test_api_video_run.py`.
- Frontend auth integration: protected mutation requests send `X-API-Key` from browser-local storage; user can set/clear it in the header. The key is never sent on public GET requests.
- Validation: Full backend suite passed `270 tests, 3 warnings` before the last incremental regression additions; the final affected backend regression subset passed `94 tests`. Frontend `npm run lint` passed with 3 existing React-hook warnings; `npm run build` passed. Core and isolated rembg dependency resolver dry-runs passed. Ruff is unavailable in the user's existing environment, and no package was installed. GitHub Actions has not been run from this workspace.

Current completion status: BUG-01–BUG-04 and BUG-06–BUG-09 have implementation and local regression evidence, but remain `[~] IN PROGRESS` until end-to-end and CI requirements are proven. BUG-05 remains `[~] IN PROGRESS`: core dependency resolver passed, and the optional rembg resolver was metadata-checked separately; clean CI installation, complete import matrix, and actual optional rembg runtime remain unverified. Do not mark the overall project submission-ready yet.

---

# 0. Objective

Dokumen ini menjadi satu-satunya backlog perbaikan bug dan reliability
sebelum submission GTNIC.

Tujuan utamanya bukan sekadar membuat aplikasi berhasil dijalankan,
tetapi memastikan seluruh komponen bekerja secara konsisten.

## Definition of Done

Sebuah bug hanya boleh dinyatakan FIXED apabila:

1. Root cause sudah ditemukan.
2. Implementasi sudah diperbaiki.
3. Regression test sudah dibuat.
4. Test terkait berhasil dijalankan.
5. Tidak menyebabkan regression pada fitur lain.
6. Perubahan sudah berhasil diverifikasi melalui workflow aplikasi.
7. GitHub Actions berhasil menjalankan backend dan frontend checks.

Status yang diperbolehkan:

- [ ] NOT STARTED
- [~] IN PROGRESS
- [x] FIXED AND TESTED
- [!] BLOCKED

Jangan menandai bug sebagai FIXED hanya karena kode sudah diubah.

---

# 1. Critical Bug Fixes

## BUG-01 — Semantic QC Return Type Mismatch

**Priority:** P0 — CRITICAL

**Affected files:**
- backend/src/carousel/tools/semantic_qc.py
- backend/src/carousel/pipeline.py

### Problem

`check_carousel_semantics()` mengembalikan tuple:

    return errors, warnings

Namun pipeline menggunakan hasilnya sebagai dictionary:

    semantic_qc_result.get("ok")

Tuple tidak memiliki method `.get()`.

Hal ini berpotensi menyebabkan AttributeError ketika pipeline
memasuki tahap semantic quality control.

Selain itu, semantic QC harus benar-benar memengaruhi keputusan
apakah hasil generation boleh diteruskan.

### Required implementation

1. Tetapkan satu kontrak return type.
2. Gunakan structured dictionary atau dataclass secara konsisten.
3. Pastikan seluruh caller mengikuti kontrak tersebut.
4. Bedakan error dan warning.
5. Error yang bersifat blocking harus menghentikan pipeline.
6. Warning non-blocking boleh diteruskan, tetapi harus dicatat.
7. Jangan menganggap QC berhasil ketika pemeriksaan gagal dijalankan.

Contoh kontrak yang disarankan:

    {
        "ok": True,
        "errors": [],
        "warnings": [],
        "checks": {
            "topic_relevance": True,
            "brand_consistency": True
        }
    }

### Required behavior

- QC pass: pipeline boleh melanjutkan generation.
- QC warning: pipeline boleh melanjutkan dengan warning tercatat.
- QC blocking error: pipeline tidak boleh melanjutkan ke approval.
- QC execution error: pipeline harus gagal secara aman.
- Hasil QC harus tersimpan atau dapat ditelusuri melalui run logs.

### Required tests

- [ ] Valid carousel returns successful QC result.
- [ ] Irrelevant carousel content produces a blocking error.
- [ ] Brand inconsistency is detected.
- [ ] Warning does not incorrectly block valid output.
- [ ] QC execution exception is handled safely.
- [ ] Pipeline never calls `.get()` on an unexpected tuple.
- [ ] Failed semantic QC prevents approval/publishing.

### Acceptance criteria

Semantic QC bekerja tanpa runtime exception dan benar-benar
menjadi bagian dari generation lifecycle.

---

## BUG-02 — PostAnalytics Model and Constructor Mismatch

**Priority:** P0 — CRITICAL

**Affected files:**
- backend/src/api.py
- backend/src/core/db.py
- analytics-related tests

### Problem

Publication endpoint mencoba membuat PostAnalytics dengan:

    publication_id=None

Namun model PostAnalytics tidak memiliki field tersebut.

Konstruktor SQLAlchemy dapat gagal karena menerima keyword
argument yang tidak dikenal.

Error juga berpotensi tertangkap oleh try/except sehingga publication
terlihat berhasil meskipun analytics record tidak tersimpan.

### Required implementation

1. Inspect the actual PostAnalytics model.
2. Inspect the actual Publication model.
3. Tentukan relasi yang benar antara publication dan analytics.
4. Jangan mengirim field yang tidak tersedia di model.
5. Jika publication_id memang dibutuhkan:
   - tambahkan field ke model;
   - buat database migration;
   - tambahkan foreign key yang sesuai;
   - perbarui seluruh query dan relationship.
6. Hubungkan analytics record dengan publication yang benar.
7. Hubungkan analytics dengan run dan strategy item jika relasinya tersedia.
8. Pastikan error pencatatan analytics tidak disembunyikan.

### Metric integrity

Jangan mengisi semua metric dengan nol hanya karena data aktual
belum tersedia.

Bedakan:

- Metric benar-benar bernilai 0.
- Metric belum tersedia.
- Metric belum berhasil diambil.
- Metric sedang menunggu sinkronisasi.

Gunakan nullable values atau status ingestion yang sesuai dengan
desain model.

### Required tests

- [ ] Successful publication creates a valid analytics record.
- [ ] Analytics record references the correct publication.
- [ ] Analytics record references the correct run where applicable.
- [ ] Analytics record references the correct strategy item where applicable.
- [ ] Missing metrics are not represented as fabricated zero values.
- [ ] Failed analytics persistence is logged and observable.
- [ ] Duplicate ingestion does not create unintended duplicate records.

### Acceptance criteria

Setiap publication yang berhasil dapat ditelusuri ke analytics
record yang benar, tanpa model mismatch atau data palsu.

---

## BUG-03 — API Authentication Is Not Applied Consistently

**Priority:** P0 — CRITICAL

**Affected files:**
- backend/src/core/auth.py
- backend/src/api.py
- backend/tests/

### Problem

Sebagian endpoint sudah menggunakan verify_api_key, tetapi
beberapa endpoint mutasi belum terlindungi.

Endpoint yang perlu diperiksa secara khusus:

- PATCH /api/v1/strategy/calendar/{item_id}
- POST /api/v1/assets/upload
- POST /api/v1/brand/logo

Calendar endpoint berpotensi mengubah approval status tanpa
authentication.

Selain itu, konfigurasi API key masih memiliki fail-open behavior
ketika GTNIC_API_KEY tidak tersedia.

CORS juga masih memiliki wildcard fallback.

### Required implementation

1. Audit seluruh API routes.
2. Kelompokkan endpoint menjadi:
   - Public endpoints.
   - Protected read endpoints.
   - Protected mutation endpoints.
3. Terapkan authentication secara konsisten pada semua protected routes.
4. Gunakan router-level dependency jika sesuai agar tidak ada
   endpoint yang terlewat.
5. Pastikan endpoint approval, upload, update, delete, dan publish
   selalu membutuhkan autentikasi.
6. Production harus gagal saat API key tidak dikonfigurasi.
7. Development mode boleh memiliki konfigurasi berbeda, tetapi harus
   eksplisit dan tidak aktif otomatis di production.
8. Jangan mengembalikan API key dalam response atau log.
9. Batasi CORS production hanya pada origin yang diizinkan.

### Required tests

- [ ] Missing API key returns 401 or 403.
- [ ] Invalid API key returns 401 or 403.
- [ ] Valid API key can access protected routes.
- [ ] Calendar approval requires authentication.
- [ ] Calendar rescheduling requires authentication.
- [ ] Asset upload requires authentication.
- [ ] Logo upload requires authentication.
- [ ] Publish endpoint requires authentication.
- [ ] Production startup fails safely without required API key.
- [ ] CORS rejects unauthorized origins.

### Acceptance criteria

Tidak ada protected mutation endpoint yang dapat diakses
tanpa authentication.

---

## BUG-04 — Upload Validation Order and Memory Safety

**Priority:** P0 — HIGH

**Affected files:**
- backend/src/api.py
- upload-related tests

### Problem

Upload validation masih memiliki dua kelemahan:

1. Seluruh file dibaca ke memory sebelum batas ukuran diperiksa.
2. Direktori dapat dibuat sebelum person_id divalidasi.

### Required implementation

1. Validate identifiers before filesystem operations.
2. Validate filename and path components.
3. Enforce upload size limits while reading chunks.
4. Stop reading immediately when the configured limit is exceeded.
5. Avoid constructing paths from untrusted user input.
6. Verify actual image format rather than trusting file extension
   or Content-Type.
7. Handle malformed and corrupted images safely.
8. Clean up temporary files after failed uploads.
9. Return clear HTTP errors for invalid uploads.

### Required tests

- [ ] Valid image uploads successfully.
- [ ] Oversized upload is rejected.
- [ ] Oversized upload does not consume unbounded application memory.
- [ ] Invalid person_id is rejected before directory creation.
- [ ] Path traversal input is rejected.
- [ ] Unsupported file format is rejected.
- [ ] Spoofed Content-Type is rejected.
- [ ] Corrupted image is rejected.
- [ ] Failed upload leaves no unintended files.

### Acceptance criteria

Upload endpoint enforces size and format restrictions before
persisting files and cannot construct unsafe filesystem paths.

---

## BUG-05 — Backend Dependency Conflict

**Priority:** P0 — CRITICAL

**Affected files:**
- backend/requirements.txt
- CI workflow
- dependency lock/constraints file if used

### Problem

Latest inspected CI failed during Python dependency installation.

Observed conflict:

- rembg 2.0.85 requires Pillow >=12.1.0 and <13.0.0.
- MoviePy 2.2.x requires Pillow >=9.2.0 and <12.0.
- Project currently specifies Pillow 12.3.0.

These constraints cannot be satisfied together.

### Required implementation

1. Inspect the current dependency versions.
2. Choose a compatible dependency combination.
3. Check official package metadata before changing versions.
4. Do not randomly downgrade or upgrade packages.
5. If necessary, replace an incompatible dependency or isolate
   optional image-processing functionality.
6. Pin tested dependency versions.
7. Prefer a reproducible lock or constraints strategy.
8. Install dependencies from a clean environment.
9. Run the complete backend test suite after installation.

### Required tests

- [ ] Clean Python environment installs backend dependencies.
- [ ] Dependency resolver reports no conflict.
- [ ] Backend imports successfully.
- [ ] API starts successfully.
- [ ] Carousel renderer imports successfully.
- [ ] Reels pipeline imports successfully.
- [ ] Image processing dependencies work.
- [ ] Backend tests execute in CI.

### Acceptance criteria

GitHub Actions installs all backend dependencies successfully
and proceeds to run pytest.

A successful dependency installation alone is not enough;
the application must also pass its tests.

---

# 2. Additional Reliability Fixes

## BUG-06 — Enterprise Context Completeness

**Priority:** P1

**Affected files:**
- backend/src/carousel/pipeline.py
- backend/src/core/db.py
- backend/src/core/strategy.py
- backend/src/carousel/agents/
- backend/src/reels/

### Problem

Enterprise profile is now used by load_brand(), but some fields
are not consistently propagated.

Fields requiring verification:

- Contact information.
- Approval workflow.
- Operating preferences.
- Products and services.
- Business goals.
- Target audience.
- Brand rules.

Profile version tracking is also not established per generation run.

### Required implementation

1. Define a canonical EnterpriseContext schema.
2. Build it from the saved EnterpriseProfile.
3. Validate required fields.
4. Pass relevant context to each agent.
5. Avoid separate inconsistent brand context construction.
6. Store profile/version reference with each generation run.
7. Ensure Carousel and Reels use the same enterprise context.

### Required tests

- [ ] Profile changes affect subsequent generation.
- [ ] Products/services reach the Planner.
- [ ] Audience and goals reach Strategy generation.
- [ ] Brand rules reach Designer.
- [ ] Approval preferences reach the approval workflow.
- [ ] Carousel and Reels use consistent context.
- [ ] Each run can identify the profile version used.

### Acceptance criteria

Enterprise profile becomes the canonical context source for the
entire application.

---

## BUG-07 — Strategy Generation Reliability

**Priority:** P1

**Affected files:**
- backend/src/core/strategy.py
- backend/src/api.py
- strategy tests

### Problem

Dynamic LLM strategy generation exists, but it still has limitations:

- Research evidence is not clearly incorporated.
- Products/services are not fully represented in the prompt.
- Historical performance is represented mainly by the latest insight.
- Template fallback remains hardcoded.

### Required implementation

1. Include complete enterprise context in the strategy input.
2. Include relevant research evidence when available.
3. Include analytics evidence with source and limitations.
4. Validate LLM output against a strict schema.
5. Handle malformed JSON and missing fields.
6. Preserve deterministic fallback behavior.
7. Clearly distinguish fallback strategy from LLM-generated strategy.
8. Store the inputs and rationale used to create the strategy.

### Required tests

- [ ] Valid LLM response creates strategy items.
- [ ] Invalid LLM response is handled safely.
- [ ] Missing API credentials trigger fallback.
- [ ] Fallback produces valid calendar items.
- [ ] Enterprise goals influence strategy output.
- [ ] Research evidence is passed to the strategy generator.
- [ ] Analytics evidence is passed when available.
- [ ] Every item has required fields and rationale.

### Acceptance criteria

Strategy generation always returns valid structured output or
a clear failure state. It must never silently create misleading
or malformed calendar items.

---

## BUG-08 — Analytics Ingestion and Feedback Integrity

**Priority:** P1

**Affected files:**
- backend/src/core/db.py
- backend/src/core/strategy.py
- backend/src/api.py
- analytics-related agents and tools

### Problem

Analytics dashboard and demo data exist, but real metric ingestion
and evidence-based feedback are incomplete.

### Required implementation

1. Separate simulated analytics from real analytics.
2. Add ingestion status and source metadata.
3. Connect platform post IDs to internal publications.
4. Store metric collection timestamps.
5. Prevent duplicate metric ingestion.
6. Handle API failures and missing permissions.
7. Generate insights from actual stored metric history.
8. Include sample size and limitations in insights.
9. Record which insight caused a strategy adjustment.
10. Never present simulated metrics as live platform data.

### Required tests

- [ ] Demo metrics are visibly labeled simulated.
- [ ] Real metrics are stored with source metadata.
- [ ] Duplicate ingestion is handled.
- [ ] Missing metrics remain distinguishable from zero.
- [ ] Insight references supporting metric records.
- [ ] Strategy adjustment references its originating insight.
- [ ] Failed ingestion is logged and retryable.

### Acceptance criteria

Analytics feedback is traceable from raw metrics to insight
to strategy adjustment.

---

## BUG-09 — Publishing and Calendar State Consistency

**Priority:** P1

**Affected files:**
- backend/src/api.py
- backend/src/core/strategy.py
- backend/src/core/db.py
- publisher modules

### Problem

Publishing lifecycle updates have been added, but the complete
state transition must be verified.

### Required implementation

1. Define allowed calendar states.
2. Validate transitions in the backend.
3. Prevent publishing unapproved content.
4. Connect calendar item to generation run.
5. Connect run to QC result.
6. Connect approval to publication.
7. Record publication success/failure.
8. Ensure failed publication does not mark the item as published.
9. Ensure retries do not create duplicate publications.
10. Keep proposed schedule separate from actual scheduled execution.

### Suggested lifecycle

    draft
      ↓
    approved
      ↓
    generating
      ↓
    needs_review
      ↓
    approved_to_publish
      ↓
    publishing
      ↓
    published

Failure states:

    generation_failed
    qc_failed
    publication_failed
    rejected

### Required tests

- [ ] Draft item cannot publish.
- [ ] Unapproved item cannot publish.
- [ ] QC failure blocks publication.
- [ ] Successful publication updates calendar state.
- [ ] Failed publication records failure state.
- [ ] Retry does not duplicate publication.
- [ ] Invalid state transitions are rejected.
- [ ] Frontend and backend show consistent status.

### Acceptance criteria

Calendar state always reflects the actual generation,
approval, and publication lifecycle.

---

# 3. Test Suite Requirements

Create or update tests under:

    backend/tests/

Required test groups:

## Authentication
- test_auth_required.py
- test_protected_routes.py

## Upload
- test_upload_validation.py

## Semantic QC
- test_semantic_qc.py
- test_semantic_qc_pipeline.py

## Analytics
- test_analytics_persistence.py
- test_analytics_ingestion.py
- test_analytics_feedback.py

## Enterprise Context
- test_enterprise_context.py

## Strategy
- test_strategy_generation.py
- test_strategy_approval.py

## Publishing Lifecycle
- test_publication_lifecycle.py

## API Integration
- test_api_integration.py

Tests should use isolated test databases and mocked external
services where appropriate.

Do not require real Instagram, Groq, Tavily, or Cloudinary
credentials to run ordinary CI tests.

---

# 4. End-to-End Verification

After unit and integration tests pass, verify the full workflow.

## Scenario A — Enterprise onboarding

- [ ] Create enterprise profile.
- [ ] Update company goals.
- [ ] Update products/services.
- [ ] Update audience.
- [ ] Update brand rules.
- [ ] Verify saved profile is used by generation.

## Scenario B — Strategy generation

- [ ] Generate a 7-day strategy.
- [ ] Verify required fields.
- [ ] Verify enterprise context is included.
- [ ] Verify research evidence is used when available.
- [ ] Verify fallback works when LLM is unavailable.

## Scenario C — Carousel generation

- [ ] Select calendar item.
- [ ] Generate carousel.
- [ ] Run ordinary QC.
- [ ] Run semantic QC.
- [ ] Verify failed QC blocks approval.
- [ ] Verify successful QC permits review.

## Scenario D — Reels generation

- [ ] Generate video.
- [ ] Run video QC.
- [ ] Verify failed QC blocks publishing.
- [ ] Verify successful QC permits review.

## Scenario E — Approval and publication

- [ ] Unapproved item cannot publish.
- [ ] Approve item.
- [ ] Publish through authorized integration or mock publisher.
- [ ] Verify publication record.
- [ ] Verify calendar state.
- [ ] Verify analytics tracking status.

## Scenario F — Analytics feedback

- [ ] Ingest or load labeled sample metrics.
- [ ] Generate an insight.
- [ ] Verify supporting evidence.
- [ ] Generate updated strategy.
- [ ] Verify strategy change is traceable to insight.

---

# 5. CI Requirements

GitHub Actions must execute:

1. Dependency installation.
2. Backend import checks.
3. Backend lint.
4. Backend unit tests.
5. Backend integration tests.
6. Frontend lint.
7. Frontend production build.

A failed step must fail the workflow.

Do not configure CI to skip tests silently when dependency
installation fails.

Before merging:

- [ ] Backend dependencies install.
- [ ] Backend tests pass.
- [ ] Frontend lint passes.
- [ ] Frontend build passes.
- [ ] No secrets are exposed in logs.
- [ ] Workflow passes on a clean runner.

---

# 6. Final Definition of Done

The project is considered ready for final submission only when:

## Critical bugs
- [ ] BUG-01 Semantic QC fixed and tested.
- [ ] BUG-02 Analytics model mismatch fixed and tested.
- [ ] BUG-03 Authentication consistently enforced and tested.
- [ ] BUG-04 Upload validation fixed and tested.
- [ ] BUG-05 Dependency conflict resolved and CI passes.

## Reliability
- [ ] BUG-06 Enterprise context verified.
- [ ] BUG-07 Strategy generation validated.
- [ ] BUG-08 Analytics ingestion and feedback verified.
- [ ] BUG-09 Publishing lifecycle verified.

## Verification
- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] End-to-end workflow passes.
- [ ] GitHub Actions passes.
- [ ] No known critical runtime errors remain.
- [ ] README setup works from a clean environment.
- [ ] Demo uses only verified functionality.

---

# 7. Instructions for the Implementing Developer or AI Agent

Follow these rules while implementing this backlog:

1. Inspect the current source before editing.
2. Do not assume the audit baseline still matches main.
3. Re-check the actual SQLAlchemy models before changing constructors.
4. Re-check all API routes before claiming authentication is complete.
5. Do not change dependencies without verifying package compatibility.
6. Add regression tests with every bug fix.
7. Do not delete existing functionality to make tests pass.
8. Do not replace real functionality with mock behavior outside tests.
9. Keep simulated demo data explicitly labeled.
10. Do not claim automatic scheduling unless a scheduler actually runs.
11. Run targeted tests after each fix.
12. Run the complete test suite before marking a section complete.
13. Update this document with evidence, test names, and CI run links.
14. If a fix is blocked, explain the blocker instead of marking it complete.
15. Re-audit the final commit before submission.

**Final rule: No feature or bug may be marked FIXED AND TESTED
without a successful test result or reproducible verification.**