# GTNIC AI Agent — Pre-Submission Development Backlog

**Repository:** jojoisstudying/GTNIC-AIAGENT  
**Branch:** main  
**Last audited commit:** 902465d0927973cf7af6bc483907fddd92960536  
**Audit date:** 2 November 2026  
**Submission deadline:** 10 November 2026

---

# 1. Project Overview

## 1.1 Product Vision
Autonomous Enterprise Social Media Operations Agent.

Sistem AI agent yang membantu perusahaan mengelola operasional media sosial melalui:
- Enterprise onboarding
- Strategy generation
- Content planning
- Trend and market research
- Carousel and Reels generation
- Quality control
- Human approval
- Content publishing
- Performance analytics
- Strategy feedback loop

## 1.2 Core Product Workflow

Enterprise Profile
    ↓
Research & Strategy
    ↓
Content Calendar
    ↓
Content Generation
    ↓
Quality Control
    ↓
Human Approval
    ↓
Publishing
    ↓
Analytics
    ↓
Strategy Feedback Loop

---

# 2. Current Implementation Audit

Status:
- [x] Implemented / appears implemented in source
- [~] Partially implemented
- [ ] Not implemented or integration not found
- [!] Bug, risk, or needs verification

## 2.1 Enterprise Workflow

**Status: PARTIAL**

### Already implemented
- [x] Enterprise profile form
- [x] EnterpriseProfile database model
- [x] API to read enterprise profile
- [x] API to update enterprise profile
- [x] Company/business context
- [x] Products and services
- [x] Target audience
- [x] Business goals
- [x] Content pillars
- [x] Brand rules
- [x] Approval workflow preferences

### Remaining work
- [ ] Make database profile the single source of truth
- [ ] Integrate complete profile into Research Agent
- [ ] Integrate profile into Strategy generation
- [ ] Integrate profile into Planner
- [ ] Integrate profile into Designer
- [ ] Integrate profile into Publisher
- [ ] Ensure Carousel and Reels use consistent enterprise context
- [ ] Track which enterprise profile/version was used in each generation run

### Acceptance criteria
- Editing enterprise information changes subsequent generated content.
- Agents receive consistent enterprise context.
- Generated content can be traced to the enterprise profile used.

---

## 2.2 Strategy & Scheduling

**Status: PARTIAL**

### Already implemented
- [x] 7-day strategy generator
- [x] Strategy/calendar frontend
- [x] Strategy API
- [x] Calendar item management
- [x] Approve/reject calendar items
- [x] Reschedule calendar items
- [x] Generate content from a calendar item
- [x] Objective field
- [x] Content pillar field
- [x] Target segment field
- [x] Content format field
- [x] Date/time field
- [x] Strategy rationale field

### Remaining work
- [ ] Replace excessive hardcoded topic templates
- [ ] Ground strategy in enterprise goals
- [ ] Ground strategy in target audience
- [ ] Ground strategy in content pillars
- [ ] Incorporate relevant research and trends
- [ ] Incorporate historical performance when available
- [ ] Store strategy inputs and reasoning
- [ ] Enforce approval requirements in backend
- [ ] Define calendar item lifecycle/state transitions
- [ ] Connect calendar item to generation run
- [ ] Connect generation run to QC
- [ ] Connect QC to human approval
- [ ] Connect approval to publication status
- [ ] Implement background scheduler if automatic timed publishing is required
- [ ] Implement timezone-safe scheduling

### Acceptance criteria
- Strategy changes according to enterprise context.
- Each calendar item has a clear objective and rationale.
- Unapproved items cannot bypass backend approval.
- Proposed posting time is distinguished from an actual scheduled publication.
- Automatic publishing is only claimed after scheduler execution is tested.

---

## 2.3 Analytics → Feedback Loop

**Status: PARTIAL — DEMO/SIMULATED DATA**

### Already implemented
- [x] PostAnalytics database model
- [x] AnalyticsInsight database model
- [x] Analytics dashboard API
- [x] Analytics frontend
- [x] Seeded demo analytics data
- [x] Insight/recommendation UI
- [x] Reference between insights and calendar items
- [x] Research Agent recent Instagram performance tool

### Remaining work
- [ ] Implement persistent ingestion of real post analytics
- [ ] Connect analytics to internal publication IDs
- [ ] Store platform post IDs
- [ ] Store metric collection timestamps
- [ ] Store metric source/provenance
- [ ] Replace or extend hardcoded insight generation
- [ ] Generate insights from actual stored metric history
- [ ] Show evidence supporting each insight
- [ ] Record sample size and limitations
- [ ] Connect insights to strategy adaptation
- [ ] Record which insight caused a strategy change
- [ ] Show resulting calendar changes

### Acceptance criteria
- Simulated metrics are clearly labeled.
- Every insight can be traced to supporting metrics.
- A strategy change can be traced to a specific insight.
- Demo does not claim simulated metrics are real Instagram data.

---

# 3. Bug & Technical Debt Backlog

## 3.1 Bugs

### BUG-01 — Brand Contrast QC
**Status:** Appears fixed in source.

- [x] Contrast QC implementation updated
- [ ] Add/verify regression tests

### BUG-02 — Missing python-multipart
**Status:** Appears fixed in source.

- [x] Dependency added to requirements
- [ ] Verify clean backend installation in CI

### BUG-03 — Reels QC Before Publishing
**Status:** Gate appears implemented.

- [x] Video QC preflight check in publishing path
- [ ] Test that failed QC blocks publishing

### BUG-04 — API Authentication
**Status:** NOT FIXED / NOT ENFORCED.

- [ ] Apply authentication to protected API routes
- [ ] Review fail-open behavior when API key is missing
- [ ] Configure production CORS restrictions
- [ ] Verify unauthorized requests are rejected

### BUG-05 — Pillow Renderer Metadata
**Status:** Appears fixed in source.

- [x] Metadata initialization improved
- [ ] Add regression test

### BUG-06 — Upload Validation
**Status:** PARTIALLY FIXED.

- [x] Image format validation
- [x] Upload size validation exists
- [x] Person ID validation exists
- [ ] Enforce size limit while streaming
- [ ] Validate identifiers before filesystem operations
- [ ] Prevent unsafe path construction

### BUG-07 — Enterprise/Brand Context
**Status:** PARTIALLY IMPROVED.

- [x] Enterprise profile form and persistence
- [ ] Complete agent integration
- [ ] Verify generated outputs change after profile edits

### BUG-08 — Carousel Semantic QC
**Status:** IMPLEMENTATION EXISTS, PIPELINE INTEGRATION NOT FOUND.

- [x] semantic_qc.py exists
- [ ] Call check_carousel_semantics() in actual pipeline
- [ ] Block invalid output where appropriate
- [ ] Add pass/fail tests

### BUG-09 — Backend CI
**Status:** FAILING.

- [ ] Inspect dependency installation error
- [ ] Fix actual dependency installation issue
- [ ] Run backend tests in CI
- [ ] Confirm pytest is not skipped

Latest inspected workflow:
https://github.com/jojoisstudying/GTNIC-AIAGENT/actions/runs/41355299121

Observed:
- Backend dependency installation failed.
- Backend pytest was skipped.
- Frontend lint/build succeeded.

### BUG-10 — Shared Carousel/Reels Lifecycle
**Status:** NEEDS REVIEW.

- [ ] Shared enterprise context
- [ ] Shared strategy brief
- [ ] Consistent approval rules
- [ ] Consistent QC lifecycle
- [ ] Consistent publication status tracking

---

# 4. Priority Development Plan

## P0 — Critical Before Submission

### P0.1 Fix Backend CI
- [ ] Inspect failed installation logs
- [ ] Resolve dependency issue
- [ ] Ensure backend tests execute
- [ ] Confirm workflow passes

### P0.2 Complete Enterprise Context Integration
- [ ] Database profile as canonical source
- [ ] Research Agent integration
- [ ] Strategy integration
- [ ] Planner integration
- [ ] Designer integration
- [ ] Publisher integration

### P0.3 Improve Strategy Generation
- [ ] Use enterprise goals
- [ ] Use target audience
- [ ] Use content pillars
- [ ] Use research evidence
- [ ] Store strategy rationale
- [ ] Reduce dependence on hardcoded templates

### P0.4 Complete Content Lifecycle
- [ ] Define state transitions
- [ ] Enforce approval in backend
- [ ] Connect calendar items to generation runs
- [ ] Connect runs to QC
- [ ] Connect QC to approval
- [ ] Connect approval to publication status

### P0.5 Fix Security and Upload Validation
- [ ] API authentication
- [ ] Production CORS configuration
- [ ] Safe API key configuration
- [ ] Streaming upload size limit
- [ ] Safe upload path validation

---

## P1 — Important for Demo Quality

### P1.1 Integrate Semantic QC
- [ ] Connect semantic QC to actual carousel generation
- [ ] Demonstrate failed QC
- [ ] Demonstrate corrected output

### P1.2 Improve Analytics Feedback Demo
- [ ] Use clearly labeled demo metrics
- [ ] Show raw metrics
- [ ] Show generated insight
- [ ] Show reasoning/evidence
- [ ] Show resulting strategy adjustment

### P1.3 Unify Carousel and Reels
- [ ] Shared enterprise context
- [ ] Shared strategy brief
- [ ] Shared review/approval rules

### P1.4 End-to-End Testing
- [ ] Enterprise onboarding
- [ ] Strategy generation
- [ ] Calendar item selection
- [ ] Research
- [ ] Content generation
- [ ] QC
- [ ] Human approval
- [ ] Publication or clearly labeled mock publication
- [ ] Analytics
- [ ] Feedback loop

---

## P2 — Optional Improvements

- [ ] Improve frontend loading states
- [ ] Improve error handling and user feedback
- [ ] Improve analytics visualizations
- [ ] Improve calendar UX
- [ ] Add campaign management
- [ ] Add advanced autonomy only when it improves a measurable workflow

---

# 5. End-to-End Demo Scenario

Use a fictional company.

## Step 1 — Enterprise Onboarding
- [ ] Enter company information
- [ ] Enter products/services
- [ ] Define target audience
- [ ] Define business goals
- [ ] Define content pillars
- [ ] Define brand rules
- [ ] Save enterprise profile

## Step 2 — Strategy Generation
- [ ] Generate 7-day strategy
- [ ] Show content objectives
- [ ] Show target audience
- [ ] Show content pillars
- [ ] Explain recommendation rationale

## Step 3 — Research
- [ ] Search relevant trends/topics
- [ ] Display sources
- [ ] Explain relevance to company context

## Step 4 — Content Generation
- [ ] Select calendar item
- [ ] Generate carousel or Reel
- [ ] Show strategy brief
- [ ] Display generated content

## Step 5 — Quality Control
- [ ] Run QC
- [ ] Show meaningful QC results
- [ ] Demonstrate a blocked failure if possible

## Step 6 — Human Approval
- [ ] Review content
- [ ] Edit if necessary
- [ ] Approve content
- [ ] Verify backend approval enforcement

## Step 7 — Publication
- [ ] Use authorized test account if configured
- [ ] Otherwise use mock publisher
- [ ] Clearly label simulated publication

## Step 8 — Analytics Feedback
- [ ] Display sample metrics
- [ ] Generate insight
- [ ] Show supporting evidence
- [ ] Show resulting strategy/calendar adjustment

---

# 6. Claims That Must Be Verified Before Use

Do not claim these features are complete without implementation and tests:

- [ ] Enterprise profile is the single source of truth for every agent.
- [ ] Strategy is fully personalized using live trends and analytics.
- [ ] Calendar automatically publishes at the selected time.
- [ ] Analytics feedback learns from real Instagram performance.
- [ ] Every carousel passes semantic QC.
- [ ] API authentication is enforced.
- [ ] Backend test suite passes.

Use accurate wording when a feature is still partial.

---

# 7. Submission Readiness Checklist

## Product
- [ ] Enterprise profile affects generation
- [ ] Strategy grounded in enterprise context
- [ ] Calendar approval lifecycle works
- [ ] Timed publishing verified or not claimed
- [ ] Demo analytics clearly labeled
- [ ] Insight produces traceable strategy adjustment
- [ ] Carousel and Reels use consistent context

## Engineering
- [ ] Backend dependencies install
- [ ] Backend tests pass in CI
- [ ] Frontend lint/build pass
- [ ] Authentication enforced
- [ ] CORS configured
- [ ] Upload validation safe
- [ ] QC integrated and tested
- [ ] README setup tested from clean environment
- [ ] No secrets committed

## Demo & Documentation
- [ ] Demo duration follows competition guide
- [ ] Every shown feature works or is labeled simulated
- [ ] Proposal matches actual architecture
- [ ] Efficiency metrics are measured, not invented
- [ ] Screenshots match current build
- [ ] Public repository works
- [ ] Demo link works
- [ ] Originality declaration completed

---

# 8. Audit Limitations

- Audit reflects commit `902465d0927973cf7af6bc483907fddd92960536`.
- Repository may have changed after this commit.
- “Appears fixed” means source review, not confirmed runtime correctness.
- No complete local deployment or end-to-end test was performed during this audit.
- Exact cause of backend CI dependency installation failure remains unconfirmed.
- Re-audit the latest main branch before final submission.