# GTNIC AI Agent — Pre-Submission Bug & Product Gap Backlog

**Repository:** `jojoisstudying/GTNIC-AIAGENT`  
**Basis:** source-code review of the repository's `main` branch.  
**Purpose:** one working checklist for fixes, missing product capabilities, and the minimum scope that should exist before the demo/submission.

> **Important:** This is a source-code audit, not a runtime test. Items marked as bugs are issues visible from the inspected code paths; they still need reproduction in a clean environment. Product gaps describe behavior that is missing or only partially represented in the current implementation. Do not claim a feature is complete until it has been tested end-to-end.

---

## 0. Executive summary

The current project already has a meaningful foundation:

- Research Agent can search external sources and request recent Instagram performance.
- Planner Agent produces a single-post plan and includes a `schedule` field in its output.
- Carousel Designer renders slides and invokes DOM-based visual QC in the HTML rendering path.
- Carousel publishing has a separate endpoint and a preflight/approval-oriented flow.
- Reels pipeline generates script, voiceover, B-roll, video composition, and video QC.
- Database records runs, research snapshots, plans, designs, assets, events, and publication records.

However, the product is not yet the full **Enterprise Social Media Operations Agent** described for the competition. The biggest product gaps are:

1. **Enterprise Workflow / Company Context** — no complete onboarding or workflow for an enterprise to describe its business, products/services, audience, goals, policies, approval chain, and constraints.
2. **Strategy & Scheduling** — the Planner creates a post and a proposed schedule field, but there is no real strategy workspace, content calendar, scheduling queue, or durable scheduling/execution workflow.
3. **Analytics → Feedback Loop** — Research can retrieve recent account performance, but there is no complete analytics module that connects published content outcomes to strategy decisions and future content plans.

These three areas are **P0 product requirements** for the intended demo. Fix the blocking bugs below as well; do not spend the remaining time polishing minor UI details before these core flows work.

---

## 1. Priority definitions

- **P0 — Must-have before demo/submission:** blocks core functionality, creates a serious security/data risk, or leaves one of the three essential product capabilities absent.
- **P1 — Should fix before submission:** reliability, validation, quality, or demo credibility issue.
- **P2 — Polish / follow-up:** useful improvement, but can be deferred if time is limited and the limitation is disclosed.

Status values used in this document:

- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented and verified by an end-to-end test
- `[?]` Needs reproduction / verification

---

# 2. P0 — Blocking bugs and release safety

## BUG-01 — Brand contrast QC can block the current brand configuration `[x]`

**Evidence in source**
- `backend/config/brand.json`
- `backend/src/carousel/tools/qc.py`
- `backend/src/carousel/agents/designer.py`

**Observed behavior**
- `check_brand()` compares `secondary` against `primary` as though the secondary color is readable text/subtext.
- Current configuration uses `secondary: #c061cb` and `primary: #1a5fb4`; their contrast is approximately 1.74:1, below the hard-coded 4.5:1 threshold.
- Designer's `warnings_blocking()` treats warnings beginning with `Kontras` as blocking.
- Therefore the current brand configuration can make the generated design fail even if the secondary color is only decorative.

**Required fix**
- Define the actual color roles: foreground text, background, decorative accent, muted text, and surface.
- Only enforce text contrast on real foreground/background pairs.
- Keep WCAG-style contrast checks for text; do not force a decorative color pair to meet a text threshold unless that pair is actually used for text.
- Add tests for passing and failing color-role combinations.
- Re-run a full carousel generation and confirm the resulting `Design.ok` and publish preflight are consistent.

**Acceptance criteria**
- The current brand palette is evaluated according to its real usage.
- A genuinely unreadable text/background pair is blocked.
- A decorative secondary color does not block the entire run by itself.

## BUG-02 — Missing `python-multipart` dependency for upload routes `[x]`

**Evidence in source**
- `backend/requirements.txt`
- `backend/src/api.py` imports and uses `UploadFile`, `File`, and `Form`.

**Observed behavior**
- Upload endpoints are declared using multipart form handling.
- `python-multipart` was not present in the inspected requirements file.
- A clean installation may fail while importing/registering the FastAPI routes.

**Required fix**
- Add a pinned compatible `python-multipart` dependency.
- Install from a clean virtual environment using only `requirements.txt`.
- Import the API application and run the upload route tests.

**Acceptance criteria**
- Clean backend installation succeeds.
- `from src.api import app` succeeds without a multipart-related runtime error.
- Logo and talent-reference upload routes can be exercised in tests.

## BUG-03 — Reels publishing does not enforce the saved video QC result `[x]`

**Evidence in source**
- `backend/src/api.py`, endpoint `POST /api/v1/runs/{run_id}/publish`
- `backend/src/api.py`, `_save_video_result()`
- `backend/src/reels/pipeline.py`

**Observed behavior**
- Video result JSON stores an `ok` value based on `VideoRunResult.ok`.
- The publish endpoint checks that the video path exists, then calls `publisher.publish_reel()`.
- The inspected Reels publish branch does not first require the stored video result to have `ok == true`.

**Required fix**
- Reject publishing unless the latest video result has `ok == true`.
- Validate that the file exists, is non-empty, and is a readable video with expected metadata.
- Make publication idempotent or explicitly prevent accidental duplicate publishing.
- Apply an approval step before publishing, consistent with the carousel workflow.

**Acceptance criteria**
- A video with failed QC cannot be published through the API.
- A missing/corrupt video cannot be published.
- Repeated publish requests do not create unintended duplicate posts.

## BUG-04 — API routes have no visible application-level authentication `[x]`

**Evidence in source**
- `backend/src/api.py`

**Observed behavior**
- The inspected API source has mutating endpoints for brand updates, uploads, generation, review, and publishing.
- No application-level authentication dependency was found in the inspected routes.
- CORS is configured with permissive origins; CORS is not authentication.

**Risk**
- If the backend is publicly reachable without platform-level or reverse-proxy protection, an unintended user could trigger generation, consume API quota, change brand data, upload assets, or publish content.

**Required fix**
- Confirm whether deployment infrastructure already protects the API.
- If not, add authentication for admin/mutating routes.
- Protect publish and credential-related operations more strictly than public read-only endpoints.
- Restrict CORS to the actual frontend origin in production.

**Acceptance criteria**
- Unauthenticated requests cannot mutate brand data, upload assets, start expensive runs, or publish.
- Deployment protection is documented and tested.

---

# 3. P0 — Essential product capabilities missing or incomplete

## FEATURE-01 — Enterprise Workflow / Company Context (MUST HAVE) `[x]`

**Current state**
- Frontend has a Brand & Asset Setup area.
- Current brand configuration includes basic fields such as company, industry, description, tone, content pillars, rules, colors, and asset/pose information.
- The current `brand.json` has an unclear/incomplete description and an empty audience field.
- There is no complete enterprise onboarding/workflow that captures the information an agent needs to operate for a company.
- There is no visible structured workflow for defining business objectives, services/products, target segments, brand constraints, approval responsibilities, and operational context.

**What the feature should do**
Create an **Enterprise Profile / Workspace Setup** flow before content generation.

Minimum input fields:
1. Company name and industry.
2. Company description — what the company does, who it serves, and what problem it solves.
3. Products/services — name, description, value proposition, and claims that are allowed to be made.
4. Target audience — segment, needs/pain points, language, location, and relevant platform.
5. Business goals — e.g. awareness, education, lead generation, recruitment, customer retention.
6. Brand identity — tone of voice, colors, logo, typography, visual references.
7. Content pillars — topics the company wants to consistently communicate.
8. Brand rules — prohibited claims, required disclaimers, sensitive topics, approved terminology.
9. Competitors / reference accounts — optional, with clear separation between inspiration and facts.
10. Contact/CTA information — website, social handle, contact details, and preferred CTA.
11. Approval workflow — who reviews content, what needs approval, and what may never auto-publish.
12. Operating preferences — preferred posting days/timezone, platforms, formats, monthly content capacity, and constraints.

**Expected agent behavior**
- Save the profile as structured, persistent company context.
- Validate required fields and show what is missing.
- Make Research and Planner consume this context, not only a generic `industry` string.
- Separate verified company facts from generated assumptions and external research.
- Let the user edit/update the profile without editing JSON files manually.
- Require human approval for official announcements, pricing, recruitment, legal/financial claims, and other sensitive company communications.

**Minimum demo implementation**
- A form/wizard to enter and save the enterprise profile.
- A company overview page showing saved profile completeness.
- At least one generation flow that demonstrably uses the entered audience, goal, products/services, content pillars, and brand rules.
- A visible indication when required company information is missing.

**Acceptance criteria**
- A new fictional company can be onboarded through the UI without editing `brand.json`.
- The saved profile survives application restart.
- Generated research and content reflect the selected audience and business goal.
- The agent does not invent company facts when profile information is missing.

## FEATURE-02 — Strategy & Scheduling (MUST HAVE) `[x]`

**Current state**
- Planner prompt asks for a `schedule` object with `slots`, `rationale`, and `ab_test`.
- Schedule slots are currently part of an individual post plan.
- Research Agent may provide suggested posting-time information.
- No complete strategy module or content calendar/scheduling queue was found in the inspected implementation.
- A proposed schedule in JSON is not the same as a scheduled post that can be reviewed, changed, and executed later.

**What the feature should do**
Create a strategy stage between enterprise onboarding/research and content generation.

Minimum strategy inputs:
- Enterprise profile and business goals.
- Target audience.
- Content pillars.
- Recent performance and available analytics.
- Campaign/topic priorities.
- Platform and content format.
- Posting frequency and available publishing capacity.
- Timezone and preferred posting windows.

Minimum strategy outputs:
1. A weekly or monthly content plan.
2. Content mix across the defined pillars.
3. Objective for each post (awareness, education, leads, etc.).
4. Recommended format (carousel, single image, Reels).
5. Topic/angle and intended audience segment.
6. Suggested publish date/time with timezone.
7. Rationale for the recommendation.
8. Priority/status and approval owner.
9. Alternative slot or A/B test when appropriate.

**Scheduling workflow**
- Show a calendar/list view of planned posts.
- Allow user to edit, approve, reject, or reschedule a planned item.
- Store scheduled items persistently in the database.
- Distinguish `draft`, `awaiting_approval`, `approved`, `scheduled`, `publishing`, `published`, and `failed`.
- Do not imply that a post is scheduled or published if the system only generated a suggested time.
- If automatic timed execution is not ready, implement a clear manual “Publish now” workflow and label future scheduling as planned/not supported.

**Minimum demo implementation**
- Generate a 7-day content calendar for a sample enterprise.
- Show each post's goal, pillar, format, date/time, and rationale.
- Allow at least one post to be edited/rescheduled and approved.
- Demonstrate that the selected calendar item is the one passed into the content-generation pipeline.

**Acceptance criteria**
- The user can see a calendar, not just a `schedule` field in raw plan JSON.
- Schedule data is stored and can be retrieved after restart.
- The system clearly distinguishes recommendation from actual scheduled execution.
- A post cannot be auto-published without the required approval state.

## FEATURE-03 — Analytics → Feedback Loop (MUST HAVE) `[x]`

**Current state**
- Research Agent has a `get_my_recent_performance` tool and requests recent Instagram performance.
- Research instructions say not to invent metrics and to report insufficient data when fewer than the required number of posts are available.
- The inspected code does not show a complete analytics dashboard or a persistent per-post analytics model linked to content strategy.
- No dedicated feedback-loop process was found that converts post results into explicit strategy changes and verifies the next plan uses those learnings.

**What the feature should do**
Create a closed loop:

`Published Post → Performance Data → Analysis → Insight → Strategy Adjustment → Next Content Plan → New Published Post`

Minimum analytics data:
- Post ID / permalink.
- Publish date/time and platform.
- Format and content pillar.
- Campaign/objective and target audience.
- Reach/impressions, likes, comments, shares, saves, profile visits/clicks where available.
- Data retrieval timestamp and source.
- Missing-data / permission / API errors.

Minimum analysis:
- Compare posts by format, pillar, objective, and publish window.
- Show trends over time, not just one isolated post.
- Identify top and weak-performing posts with context.
- Avoid comparing metrics that are not comparable (e.g. reach vs impressions).
- State when the sample size is too small.
- Distinguish correlation from causation.
- Avoid claiming that a posting time or format caused performance changes without sufficient evidence.

Minimum feedback output:
- 2–3 actionable insights, each tied to observed data.
- A recommendation for what to test next.
- A confidence/data-sufficiency label.
- A record of which insight influenced the next strategy or plan.

**Minimum demo implementation**
- Use authorized real account metrics if available; otherwise use a clearly labeled sample dataset.
- Display a small analytics view with at least post-level metrics and comparisons.
- Generate an insight from those records.
- Show the next strategy/calendar plan changing because of that insight.
- Preserve the original metric values and source; do not fabricate engagement results.

**Acceptance criteria**
- Analytics data is stored with post/run identifiers.
- An insight can be traced back to the underlying metrics.
- A later strategy/plan references the insight that influenced it.
- When data is insufficient, the agent explicitly says so and does not invent a conclusion.
- Demo data is labeled as sample/simulated if it is not fetched from a real account.

---

# 4. P1 — Other bugs and reliability issues

## BUG-05 — Pillow renderer branch may access `meta["issues"]` before it exists `[x]`

**Evidence**
- `backend/src/carousel/agents/designer.py`

**Observed behavior**
- In the `renderer_mode != "html"` branch where a layout renderer is used, the returned `meta` receives `role` and `index`.
- The inspected branch does not initialize `meta["issues"]` in the same way as the HTML branch.
- Later shared code may access `m["issues"]`, which can raise `KeyError` for that renderer path.

**Required fix**
- Initialize a consistent metadata schema for every renderer branch, including `issues`, `dom_issues`, `path`, and other fields consumed downstream.
- Add a test using `RENDERER=pillow` and a plan with `layout_id`.

## BUG-06 — Talent-reference upload lacks visible file validation and size limits `[x]`

**Evidence**
- `backend/src/api.py`, `/api/v1/assets/upload`
- `backend/src/api.py`, `/api/v1/brand/logo`

**Observed behavior**
- The inspected routes read uploaded bytes and write them to predictable paths.
- No clear upload-size cap, MIME allowlist, actual image decoding/verification, or dimension check was visible in these route implementations.
- `person_id` is used to build a filesystem path and should be validated.

**Required fix**
- Enforce a maximum upload size.
- Validate actual file contents as an image (not only the submitted MIME type).
- Restrict accepted formats and dimensions.
- Sanitize/allowlist `person_id`; prevent path traversal.
- Use safe temporary files and atomic replacement.
- Return clear validation errors.

## BUG-07 — Brand profile data quality is incomplete `[x]`

**Evidence**
- `backend/config/brand.json`

**Observed behavior**
- `description` begins with an apparent typo/incomplete phrase.
- `audience` is empty.
- The description does not clearly establish the demo company's actual products/services and positioning.
- A phone number is present in the footer configuration; verify it is an intended public business contact before exposing it in a public demo.

**Required fix**
- Complete the sample enterprise profile.
- Add a realistic audience, value proposition, product/service facts, and approved CTA.
- Keep sample company data fictional or explicitly authorized.
- Ensure all public contact details are intentional.

## BUG-08 — Carousel-level semantic QC is incomplete `[x]`

**Current state**
- DOM-based QC is already called in the main HTML rendering path.
- Existing checks include layout/fit/overflow-related checks and other visual diagnostics.
- Do not rebuild this from scratch.

**Gap**
Current slide-level technical QC does not by itself prove that the entire carousel is coherent, accurate, and useful.

**Required additions**
1. Role/order validation: cover → content → CTA.
2. Narrative progression across slides.
3. Duplicate/repeated information detection.
4. Headline/subtext/slot consistency.
5. Caption matches the carousel content.
6. Sources support factual claims and statistics.
7. Brand typography/colors/logo remain consistent across slides.
8. Images/assets are relevant and correctly associated with the content.
9. Output file exists, is readable, and has expected dimensions.
10. Any automatic repair/regeneration must run QC again.

**Implementation guidance**
- Use deterministic checks for structure, dimensions, missing files, source URL membership, and repeated text.
- Use an LLM only for semantic review (coherence, relevance, misleading claims), with a structured result and explicit uncertainty.
- Keep the existing DOM QC as the visual/layout layer.
- Separate `error` (blocks approval) from `warning` (human review).

## BUG-09 — No CI workflow was visible in the inspected repository tree `[x]`

**Observed behavior**
- No `.github/workflows` files were found in the inspected tree.
- The repository contains backend tests and frontend build/lint scripts, but there was no visible automated workflow tying them together.

**Required fix**
Add a basic GitHub Actions workflow that:
- Installs backend dependencies.
- Runs backend tests.
- Installs frontend dependencies.
- Runs frontend lint and production build.
- Fails the workflow if any required check fails.

If CI cannot be completed before the deadline, run and record these checks manually before submission.

## BUG-10 — Reels and Carousel do not yet share a unified strategy/publishing lifecycle `[x]`

**Observed behavior**
- Carousel generation has a Research → Planner → Designer flow.
- Reels has a separate Scriptwriter → TTS → B-roll → Composition → QC flow.
- The Reels pipeline does not appear to consume the same complete content strategy/calendar object as Carousel.
- The publish endpoint has a Reels branch, but its QC gate needs the fix described in BUG-03.

**Required fix**
- Make both formats receive a common content brief: goal, audience, pillar, campaign, key message, CTA, source constraints, and planned publish slot.
- Keep format-specific production pipelines, but store both outputs against the same strategy/calendar item.
- Enforce the same approval and publication state model for both formats.

---

# 5. P1 — Product consistency and agent behavior

## GAP-01 — Research findings are not yet a durable learning system

- Recent performance is requested during research, but there is no complete, traceable analytics history and insight store.
- Persist raw metrics, normalized metrics, analysis, and the strategy decision that used each insight.
- Do not rely on the LLM's conversational summary as the only memory of past performance.

## GAP-02 — Planner is post-oriented, not campaign/strategy-oriented

- The current prompt asks for one Instagram post at a time.
- A `content_pillar` field is useful, but it is not a complete strategy.
- The Planner should receive an approved campaign/strategy brief and produce an item that belongs to a calendar.
- Avoid generating isolated content without knowing the enterprise goal and planned content mix.

## GAP-03 — Scheduling recommendation is not scheduling execution

- A time written in `schedule.slots` is a recommendation.
- A true scheduler needs persistent scheduled records, timezone handling, status transitions, retry policy, and a worker/cron mechanism.
- If this cannot be implemented safely before the demo, present it honestly as a proposed calendar with manual approval/publish.

## GAP-04 — Enterprise approval workflow needs explicit states and responsibilities

- Asset review exists, and carousel publishing has a preflight check.
- The product still needs a clear business-content approval workflow.
- Define who may approve, which content categories require approval, what happens after rejection, and how changes are audited.
- Do not treat asset approval as equivalent to approval of the final post.

## GAP-05 — No visible dedicated analytics interface

- The frontend should expose analytics and insights, not only generation, brand settings, assets, and run history.
- At minimum, include performance cards/table, filters, insight summaries, and “used in next strategy” traceability.

---

# 6. P2 — Submission polish

## POLISH-01 — Frontend package metadata `[x]`
- `frontend/package.json` still uses a generic package name (`temp-app`) and version `0.0.0`.
- Rename it to a project-appropriate package name and set a sensible initial version.

## POLISH-02 — Documentation must match implemented behavior
- Review README and technical documentation against the actual UI and API.
- Clearly label features as implemented, partially implemented, planned, or simulated.
- Do not describe a recommendation as an automated schedule.
- Do not describe a sample analytics dataset as real Instagram performance.
- Do not claim Reels publishing is QC-safe until BUG-03 is fixed and tested.

## POLISH-03 — Public demo environment
- Confirm frontend and backend are both publicly reachable.
- Confirm environment variables are configured without exposing secrets.
- Confirm static media URLs work from outside the local machine.
- Confirm the demo does not depend on local-only files or a developer's personal account.
- Have a fallback demo dataset/media in case external APIs fail.

---

# 7. Recommended build order before the demo

The order below prioritizes a coherent, judge-visible product rather than trying to build every possible feature.

## Phase A — Remove blockers

- [ ] BUG-01: fix brand contrast QC semantics and tests.
- [ ] BUG-02: add `python-multipart`; verify clean API import.
- [ ] BUG-03: block Reels publishing when QC failed; add approval/idempotency guard.
- [ ] BUG-04: verify deployment auth or add API protection.
- [ ] BUG-07: complete and sanitize the demo enterprise profile.

## Phase B — Build the three core product capabilities

- [ ] FEATURE-01: Enterprise Profile / Workflow form and persistence.
- [ ] FEATURE-02: Strategy generator + 7-day calendar + edit/approve/reschedule.
- [ ] FEATURE-03: Analytics view + traceable insights + feedback into next strategy.

**Recommended dependency order:** Enterprise Profile → Strategy & Scheduling → Analytics Feedback Loop.  
Analytics should feed the next strategy, so the strategy model and content/calendar identifiers should be established before implementing the feedback loop.

## Phase C — Improve content trust and reliability

- [ ] BUG-08: carousel-level semantic/content QC.
- [ ] BUG-05: fix and test Pillow renderer metadata.
- [ ] BUG-06: validate uploads and filesystem paths.
- [ ] BUG-09: add CI or record clean manual test results.
- [ ] BUG-10: unify Carousel/Reels around a common strategy brief and approval lifecycle.

## Phase D — Demo readiness

- [ ] Complete one end-to-end fictional enterprise onboarding.
- [ ] Generate a strategy/calendar for that company.
- [ ] Generate one Carousel and one Reels item from the strategy.
- [ ] Show visual/content QC and human approval.
- [ ] Show analytics data (real authorized data or clearly labeled sample data).
- [ ] Show at least one analytics insight influencing the next strategy.
- [ ] Publish only to an authorized test account, or use a clearly labeled simulated publishing step.
- [ ] Run backend tests and frontend build/lint.
- [ ] Verify public deployment and demo video.

---

# 8. Minimum end-to-end story the demo should prove

Use one fictional enterprise (for example, a small Indonesian cybersecurity/software company) and demonstrate this sequence:

1. **Onboard the enterprise:** enter what the company does, services, audience, goals, brand voice, content pillars, restrictions, and approval rules.
2. **Create strategy:** agent recommends a 7-day plan with goals, pillars, formats, and publish windows.
3. **Review calendar:** user edits one item and approves it.
4. **Generate content:** select a calendar item; Research and Planner use the saved enterprise profile and strategy.
5. **Produce assets:** create Carousel or Reels.
6. **Run QC:** show technical and content checks; block a failed output.
7. **Approve and publish:** human approval, then authorized publishing or clearly labeled simulation.
8. **Analyze performance:** show post metrics with source and data timestamp.
9. **Close the loop:** agent produces an evidence-based insight and adjusts a future calendar item.

The key differentiator is not simply that the system can generate a post. It should demonstrate that it can understand a company's operating context, plan content around business goals, execute through tools, check its own output, and learn from measurable outcomes.

---

# 9. Test checklist

## Backend
- [ ] Clean dependency install from `backend/requirements.txt`.
- [ ] API imports successfully.
- [ ] Brand profile create/update/reload works.
- [ ] Upload rejects invalid, oversized, and unsafe files.
- [ ] Research handles API failure, insufficient performance data, and invalid model output.
- [ ] Planner validates content, source references, schedule fields, and layout roles.
- [ ] HTML renderer and Pillow renderer both complete without metadata errors.
- [ ] Brand QC blocks only genuinely inaccessible text/background combinations.
- [ ] Carousel semantic QC blocks duplicate/incoherent/unsupported content.
- [ ] Failed Reels QC cannot reach publishing.
- [ ] Approval and publishing states are persisted correctly.
- [ ] Duplicate publish request is handled safely.
- [ ] Analytics records link to the correct publication and run.
- [ ] Feedback insight can be traced to metrics and a subsequent strategy change.

## Frontend
- [ ] Enterprise onboarding form works and persists data.
- [ ] Missing profile fields are visible.
- [ ] Strategy/calendar is visible and editable.
- [ ] Approval/rejection/reschedule states are clear.
- [ ] Analytics dashboard displays source and timestamp.
- [ ] Feedback insights are connected to the next strategy.
- [ ] Run events and errors are understandable to a non-technical enterprise user.
- [ ] Mobile/responsive layout is usable for the demo.

## Deployment and demo
- [ ] Public frontend URL works.
- [ ] Backend API is reachable only through intended access controls.
- [ ] Static generated media can be loaded publicly when required.
- [ ] No secrets are committed or shown in logs/screenshots.
- [ ] Demo works if one optional external API is unavailable.
- [ ] All simulated data/actions are explicitly labeled.
- [ ] Demo video is within the required duration and shows the actual deployed product.

---

## 10. Scope discipline

Do not try to build a massive enterprise platform before the deadline. The minimum convincing version is:

- One complete enterprise profile.
- One strategy workflow that generates and stores a 7-day calendar.
- One analytics view with traceable insights.
- One feedback action that visibly changes the next strategy.
- One reliable content-generation and QC path.
- Human approval before publishing.

Anything beyond this can be documented as future development. The three core capabilities must be visible in the product, not only mentioned in the proposal.
