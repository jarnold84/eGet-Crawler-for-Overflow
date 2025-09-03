TL;DR
You can extend the existing eGet Website Crawler (Scraper 2) so that it does everything the 3‑SS design calls for – names, emails, socials, pagination, profile‑page discovery, and per‑lead coordination. It will require a modest amount of engineering (roughly 2 – 3 working days for a solid MVP) because the bulk of the heavy lifting (HTTP fetching, Playwright rendering, politeness, robots‑txt handling) is already in place.

Below is a step‑by‑step roadmap, the why behind each change, and a time‑box estimate. I also point out where you might still want to keep a dedicated “Contact‑Info Scraper” (your current open‑source Scraper 1) as a fallback for especially noisy sites.

1️⃣ High‑level architectural decision
Option	What you keep	What you add / modify	Pros	Cons
A – Extend eGet only	Use eGet as the sole crawler for both profile‑content and contact fields.	Add selector‑driven name/email/social extraction, depth‑2 list → profile logic, lead‑coordination, optional AI fallback.	One codebase, single deployment, easier orchestration, consistent provenance (sourceUrls).	Slightly larger surface area; you still may want a lightweight “quick‑email” scraper for ultra‑fast single‑page sites.
B – Keep 3‑SS as‑is	Keep Scraper 1 (pre‑built contact scraper) + Scraper 2 (eGet) + Scraper 3 (AI).	Only glue code to merge results downstream.	Proven contact‑scraper already tuned for email/phone extraction; less risk of breaking it.	Two actors to maintain, duplicated crawling of the same pages (extra cost, extra latency).


Recommendation	Start with Option A (extend eGet) and keep Scraper 1 as a fallback that you can disable for sites where eGet succeeds. This gives you the “single‑actor” simplicity while preserving a safety net for the hardest cases.			
2️⃣ Concrete changes to eGet (the “Website Content Crawler”)
Below each change I note what file/module you’ll likely touch, why it matters, and a rough effort.

2.1 Add a campaign‑driven selector model
File(s): configs/selectors.yaml (new) + services/crawler/config_loader.py (new).
What it does: Stores, per campaign (e.g., faculty_directory, photographer_portfolio, generic_business), the CSS/XPath selectors for:
List‑page link selectors (how to find profile URLs on a roster page).
Pagination selectors (rel=next, .pager a, ?page= patterns).
Profile‑page field selectors for name, email, phone, socials, title, organization, etc.
Why: Keeps the crawler data‑driven; you can add a new vertical without touching Python code.
Effort: 2 h to draft the YAML schema and a tiny loader that returns a CampaignConfig object.
2.2 Create a Lead model with provenance
File(s): models/lead.py (new).
What it does: Mirrors the JSON schema you posted (name, email, socials, services, sourceUrls, profileLink, etc.). Each field is a Optional[...] plus a parallel sourceUrls dict that records the page(s) that yielded the value.
Why: Guarantees field‑level source URLs (a core requirement of the 3‑SS spec) and makes downstream merging trivial.
Effort: 1 h (Pydantic model + dict helpers for adding provenance).
2.3 Implement profile‑page extraction (profile_extractor.py)
File(s): services/crawler/profile_extractor.py (new).
What it does:
Receives a profile URL + the CampaignConfig.
Fetches the page (via existing Playwright/requests wrapper).
Runs the field selectors, populates a Lead instance, and records each selector’s source URL.
Falls back to regex‑based email/phone detection if a selector is missing (covers sites that hide contact info in plain text).
Why: Centralises all deterministic extraction in one place; makes it easy to unit‑test.
Effort: 3 h (selector application, regex fallback, unit tests).
2.4 Add depth‑2 crawl orchestration (crawler_service.py)
File(s): services/crawler/crawler_service.py (modify).
What it does:
Starts from the seed URL (the directory or homepage).
Uses the list‑page selectors to collect profile URLs.
Applies pagination selectors until max_pages or max_requests limits are hit.
De‑duplicates URLs (canonicalization).
Calls profile_extractor for each discovered profile URL (concurrently, respecting the existing concurrency caps).
Returns a list of Lead objects plus any “orphan” leads that were found on a list page without a dedicated profile (block‑split fallback – see 2.6).
Why: This is the core “list → profile” flow the 3‑SS spec demands.
Effort: 4 h (queue handling, pagination loop, concurrency, error handling).
2.5 Expose the campaign parameter in the API request model
File(s): models/crawler_request.py (add campaign: str = "generic").
File(s): main.py (FastAPI) – update /crawl endpoint to accept the new field and pass it to CrawlerService.
Why: Allows you to pick the right selector set at runtime (e.g., campaign="faculty").
Effort: 30 min.
2.6 Add block‑splitting for list pages that lack individual profile links
File(s): services/crawler/block_splitter.py (new).
What it does:
Parses the HTML of a list page, looks for repeating card‑like containers (<div class="card">, <li>, etc.).
Runs the same NER/email regexes on each block’s text to generate multiple Lead objects that share the same pageUrl but have distinct sourceUrls.
Why: Faculty directories often embed several people on a single page without separate URLs.
Effort: 2 h (simple heuristic + unit test).
2.7 Add optional AI fallback hook (Scraper 3)
File(s): services/fallback_ai.py (new, thin wrapper).
What it does:
Receives a Lead with missing high‑priority fields (name, email, at least one contact).
Calls your chosen LLM endpoint (OpenAI, Anthropic, etc.) with a deterministic prompt that asks for the JSON schema plus source URLs (you can reuse the prompt you already have for Scraper 3).
Merges the AI‑generated fields back into the Lead.
Why: Keeps the “edge‑case” capability inside the same actor, so you can run a single‑pass pipeline when you want (e.g., for a quick proof‑of‑concept).
Effort: 2 h (prompt design, API wrapper, rate‑limit handling).
2.8 Update output format (JSON Lines + optional markdown)
File(s): models/crawler_response.py (extend with leads: List[Lead]).
File(s): run.py (Apify actor) – after the crawl finishes, push the list of leads to the Apify dataset (or stream as JSON‑Lines).
Why: Matches the schema you posted and makes downstream merging trivial.
Effort: 1 h.
2.9 Write minimal pytest suite
Tests:
List‑page pagination & profile‑URL discovery.
Profile extraction for a sample page (assert name/email/socials + sourceUrls).
Block‑split fallback on a mock multi‑lead list page.
AI fallback stub (mocked LLM response).
Why: Guarantees that each new piece works in isolation and prevents regressions when you later tweak selectors.
Effort: 2 h.
2.10 Documentation & sample campaign YAML
File: configs/selectors.yaml – include at least three starter campaigns (faculty, photographer, generic).
README section describing how to add a new campaign.
Effort: 1 h.
3️⃣ Time‑boxed roadmap (full MVP)
Day	Tasks (approx.)	Cumulative hrs
Day 0	Set up a branch, run existing eGet tests, confirm baseline works.	1
Day 1	1️⃣ Selector model + config loader (2 h) 2️⃣ Lead model (1 h) 3️⃣ Profile extractor (3 h)	6
Day 2	4️⃣ Depth‑2 crawl orchestration (4 h) 5️⃣ API request update (0.5 h) 6️⃣ Block‑splitter (2 h)	12.5
Day 3	7️⃣ AI fallback wrapper (2 h) 8️⃣ Output response & Apify dataset push (1 h) 9️⃣ Pytest suite (2 h) 10️⃣ Docs & sample YAML (1 h)	18.5
Buffer	Bug‑fixes, logging polish, CI integration	~2 h
Total	≈ 20 hours (~2½ working days)	
If you want a leaner version (skip AI fallback and block‑split for now) you can shave ~4 h, bringing the MVP down to ~16 h.

4️⃣ Where to keep Scraper 1 (the pre‑built contact scraper)
Even after extending eGet, there are two scenarios where the original contact‑scraper remains valuable:

Situation	Why keep it
Ultra‑fast single‑page sites (e.g., a photographer’s landing page with a visible mailto:)	The contact scraper can pull the email in < 100 ms without launching the full depth‑2 crawl.
Sites that deliberately hide contact info behind JavaScript that eGet’s Playwright rendering struggles with (heavy SPA, Cloudflare challenges)	The open‑source scraper you already have may have custom anti‑bot tricks or a different headless engine that succeeds where eGet times out.
Cost‑control	Running the cheap contact scraper first, then falling back to the heavier eGet only when it reports “no leads found”, reduces overall compute spend.
Implementation tip: In the Apify actor’s run.py, call the contact scraper first; if it returns ≥ 1 lead with a valid email/phone, skip the depth‑2 crawl for that domain. Otherwise, invoke the extended eGet pipeline.

5️⃣ How the extended eGet fits the 3‑SS “ideal output”
Field (from your JSON schema)	Source after extension
name, title/role, businessName	Extracted by profile selectors or NER on block text.
email, phone, socialHandles.*	Regex fallback + selector‑driven extraction on profile pages.
servicesOffered, styleVibeDescriptors, location, valuesMissionStatement, portfolioLinks, bookingContactLinks, testimonialsSocialProof	Same as before – eGet already returns raw page text; you add deterministic regex/keyword selectors for the most common patterns.
rawPageText	Already provided by eGet (markdown/html).
sourceUrls (per field)	New – every extraction routine records the URL that produced the value.
profileLink	The URL of the profile page (or the list‑page URL when block‑splitting).
confidence (optional)	Simple scoring: +5 for email, +4 for name, +2 per social, +3 for services, etc. (you can add this later).
Thus the single‑actor eGet‑extended pipeline can deliver exactly the JSON you described, with the same granularity and provenance that the 3‑SS spec requires.

6️⃣ Quick checklist for you before you start
Clone the eGet repo on a fresh branch.
Verify you can run the existing FastAPI /crawl endpoint locally.
Install pydantic, pytest, and any missing dev deps.
Create a configs/ folder (git‑ignore the YAML if you want to keep it secret).
Draft the first campaign (generic) with a few universal selectors:
generic:
  list_selectors:
    - "a[href*='/team/'], a[href*='/people/']"
  pagination_selectors:
    - "a[rel='next']"
    - "a.next"
  profile_fields:
    name: "h1, .person-name"
    email: "a[href^='mailto:']"
    phone: "a[href^='tel:'], .phone"
    socials:
      instagram: "a[href*='instagram.com']"
      twitter: "a[href*='twitter.com']"
      linkedin: "a[href*='linkedin.com']"
Run the unit tests after each major change; they’ll catch selector‑lookup errors early.
7️⃣ Bottom line
Yes – eGet can be turned into the “universal” scraper you need.
The work is mostly additive (selectors, a Lead model, depth‑2 orchestration) and fits cleanly into the existing codebase.
Estimated effort: ~20 hours for a production‑ready MVP that covers pagination, profile discovery, multi‑lead pages, and per‑field source URLs.
Recommended workflow: Extend eGet as described, keep your current contact‑scraper as a cheap first‑pass fallback, and optionally invoke the AI fallback only when the deterministic pipeline fails to meet the confidence threshold.
Let me know which part you’d like to dive into first (e.g., the selector YAML design, the profile‑extractor implementation, or wiring the depth‑2 crawl), and I can provide a concrete code snippet to get you started!


4 files

Overflow Universal Scraper – Triple Scraper System
Overview

The Overflow Universal Scraper – Triple Scraper System is a modular, multi-scraper data extraction pipeline designed to capture and consolidate contact and contextual information from diverse websites with minimal manual intervention. Leveraging a triple-layer architecture—Contact Info Scraper, Website Content Crawler, and AI Fallback Agent—the system achieves a 90%+ success rate across both simple and complex site structures (single-lead and multi-lead). It outputs clean, schema-compliant data optimized for integration into automation workflows and business systems.

Purpose

The system provides a universalized, automated approach to lead and context scraping, reducing the need for custom code or per-site adjustments. It is purpose-built for users targeting diverse verticals—such as freelancers, musicians, therapists, nonprofits, and academic institutions—who need structured, reliable data (emails, names, phones, socials, and contextual descriptors) consolidated into a single, auditable dataset.

Specifications

Architecture: Triple scraper pipeline with modular components

Scraper 1: Contact Info Scraper (emails, phones, socials)

Scraper 2: Website Content Crawler (names, roles, services, context via NER)

Scraper 3: AI Agent (fallback for edge cases and low-confidence outputs)

Integration Layer: Make (Integromat) for orchestration, deduplication, merging, QA, and scoring

Database/Storage: Google Sheets for final lead table + Apify Datasets for raw/staging data

Supported Outputs: JSON schema per lead with field-level source URLs

Automation Settings: Standard routing, pseudoURLs, auto-pagination, domain-scoped depth rules

Validation: Optional NeverBounce email verification between merging and deduplication steps

Confidence System: Scoring model with configurable thresholds for halting or triggering fallback

Features

Triple Scraper Workflow: Combines deterministic scrapers with AI fallback for near-universal coverage.

Automated Pagination: Handles multi-page directories and deep navigational structures.

Multi-Lead + Single-Lead Handling: Generates one record per person, even when multiple people appear on one page.

Field-Level Attribution: Source URLs stored for each extracted value for transparency and auditing.

Configurable Campaign Modes: Route and keyword maps for verticals (wedding, corporate, mixed, universal).

Confidence Scoring + Stop Rules: Prevents over-crawling once leads are sufficiently complete.

Deduplication Logic: Ensures one unique record per person using profile link, email, or name+domain hash.

Automation-First Design: Minimal manual setup; fallback AI engaged only when necessary.

QA Dashboard: Weekly reporting of low-confidence or incomplete records for targeted review.

Benefits

High Coverage: 90%+ automation success across varied site types.

Minimal Manual Work: Standardized settings reduce per-site configuration.

Scalable: Concurrency, proxy support, and page limits make it deployable at scale.

Structured Output: JSON/Sheets outputs conform to a universal schema.

Audit-Ready: Every data field carries its original source URL.

Adaptable: AI fallback ensures even edge cases yield structured results.

Time-Saving: Reduces weeks of manual scraping or custom script development.

Definition of Done

A deployment or run is considered complete and ready when:

All input domains have been processed through all three scrapers.

Every discovered lead has a single, deduplicated row in Google Sheets and Apify Dataset.

Required fields (name + ≥1 contact channel) are present for ≥70% of leads.

Confidence score meets or exceeds the configured threshold for ≥90% of leads.

Source URLs are populated for all non-empty fields.

Low-confidence or missing-lead records are automatically flagged for fallback AI or review.

QA dashboard shows successful completion with error/exception logs <10% of input sites.

Use Cases

Faculty Directories: Extract all professors with emails, phones, office addresses, and publication links.

Freelancers/Photographers: Pull individual contact and contextual data (services, vibe, testimonials).

Therapists/Coaches: Capture bios, services, and mission statements alongside validated contacts.

Nonprofits/Professional Orgs: Harvest leadership/team pages for outreach and partnership mapping.

Music Venues/Artists: Collect booking info, social links, and performance portfolio data.

Integrations

Internal

Apify Actors: Contact Details Scraper, Website Content Crawler

Overflow pipeline components (DomainContext, CampaignMode, QA Dashboard)

External

Make (Integromat): Orchestration, merging, deduplication, fallback routing, scoring

Google Sheets: Final database of leads, staging, QA dashboards

NeverBounce: Email verification for higher accuracy

Slack/Email Alerts: Notifications of low-confidence or failed runs

Optional CRM/Notion/Database Sync: Downstream lead management integrations

Main Workflow Overview

Input Collection: Load domains or homepage URLs into Google Sheets or Apify.

Scraper 1 – Contact Info Scraper: Collect emails, phones, social links.

Scraper 2 – Website Content Crawler: Crawl high-signal routes (/about, /team, /faculty, etc.), return raw text/HTML.

NER/LLM Processing: Extract names, roles, services, mission, location from pageText.

Merge + Score: Join results by profile URL, email, or name+domain; calculate confidence.

Email Validation: Run NeverBounce on emails before deduplication.

Deduplication: Keep one record per person with the highest score.

Fallback (Scraper 3 – AI Agent): If score < threshold or missing essentials, invoke AI to fill schema.

Finalization: Write clean, per-lead records into Google Sheets (Final tab) and Apify Dataset.

QA & Monitoring: Weekly dashboard checks, alerts, and re-queueing of flagged domains.

*******

Overflow Universal Scraper - Triple Scraper System Features & Specs

**Three-scraper, Apify-first system for 90%+ automated success across diverse websites**

---

## 1) Objective, Success Criteria, and “Done” Definition

### Objective

Build an **automated, low-touch pipeline** that extracts and merges **person-level** and **business-level** lead data from the open web—covering **single-lead** sites (e.g., freelancers) and **multi-lead** sites (e.g., faculty/staff directories)—with **90%+ success** in retrieving **names, contact info, socials, and contextual fields** (services, location, mission/values, portfolio, booking, testimonials), and **field-level source URLs** for auditability.

### Success Criteria (how we measure “90%+”)

* **Zero-tuning coverage**: ≥ **80%** of domains run to completion with **no per-site tweaking** (routes, selectors).
* **Lead completeness**: ≥ **70%** of discovered leads contain **name + at least one contact channel (email/phone/social)** + **profile/source links** + **≥1 contextual field** (services/location/mission/portfolio/booking/testimonials).
* **Confidence**: Average **confidence score ≥ 10** (on the scoring rubric below).
* **Throughput**: Scales to **thousands of domains** with **concurrency**, **proxy rotation**, and **auto-pagination** without manual babysitting.
* **Ops simplicity**: Weekly QA review < **1 hour**; < **10%** of sites require manual follow-up.

### “Done” Definition (crisp)

* The system processes an input list of domains and **outputs one clean row per lead** into **Google Sheets** (plus an **Apify Dataset** mirror), matching the **JSON schema** in §4, with:

  * **No duplicates** (dedupe enforced).
  * **Per-field `sourceUrls`** populated where values exist.
  * **Automatic fallback** to an **AI agent** for low-yield pages/sites.
  * **Automatic flags** for failures or low-confidence leads.
  * **Schedules, alerts, and dashboards** active.

---

## 2) System Overview (Three Scrapers + Orchestration)

**Scraper 1 – Contact Details Scraper (Apify / vdrmota)**
Goal: High-coverage extraction of **emails**, **phones**, and **social links** across domain pages.

**Scraper 2 – Website Content Crawler (Apify / apify/web-content-crawler)**
Goal: Route-aware crawling of **/about**, **/team|/people|/faculty**, **/contact**, **/services|/weddings|/events**, etc., returning **pageText/rawHTML** for **names (NER)** and **contextual fields** (services, mission/values, location, booking/testimonials, portfolio).

**Scraper 3 – AI Agent (fallback)**
Goal: When Scraper 1+2 yield **incomplete** data or **unusual structure**, run an **LLM extraction pass** over the raw text/HTML to fill **names & context** with **structured JSON** (bounded tokens, deterministic prompts).

**Other Tools**

* **Make**: end-to-end orchestration, merging, normalization, scoring, dedupe, QA flags, scheduling, error notifications.
* **Google Sheets**: canonical **Lead table** (1 row/lead), plus **staging tabs** for Scraper 1 & 2 outputs and QA dashboards.
* **Apify Datasets**: storage of raw outputs and merged JSON for export and audit.

---

## 3) High-Level Architecture & Data Flow

1. **Input**: A sheet or list of **start URLs/domains**.
2. **S1 run** (Contact Scraper): extract **emails/phones/socials** per page; dataset → **Sheet A**.
3. **S2 run** (Content Crawler): crawl target routes + pagination; return **raw text/HTML + URLs**; dataset → **Sheet B**.
4. **Make (Merge Stage 1)**:

   * **Normalize** domains, URLs, and social handles.
   * **Block splitting** for multi-lead pages (team/faculty listing).
   * **NER/LLM** on text blocks to **extract names, titles, roles**; infer services/location/mission.
5. **Make (Merge Stage 2)**:

   * **Join** S1 & S2 by primary key **`pageUrl`** (profile pages) → fallback keys: **`profileLink`**, **`email`**, **`name+domain`** (fuzzy).
   * **Per-field source URL** attribution from the originating page(s).
6. **Scoring & Stop Rules**: assign **confidence score**; auto-flag low scores.
7. **AI Fallback** (S3): low-yield domains/pages → **LLM extraction** pass returns schema-compliant JSON with provenance.
8. **Dedupe & Finalization**: person-level unique rows; **one lead = one row**.
9. **Output**: save to **Google Sheets (Final Leads)** and **Apify Dataset (Merged)**.
10. **Ops**: **Schedules**, **alerts**, **QA report** (missed fields, low confidence, error counts).

---

## 4) Data Model (Per-Lead JSON Schema)

```json
{
  "name": "string",
  "businessName": "string",
  "email": "string",
  "phone": "string",
  "socialHandles": {
    "instagram": "string",
    "tiktok": "string",
    "threads": "string",
    "twitter": "string",
    "facebook": "string",
    "linkedin": "string",
    "youtube": "string"
  },
  "servicesOffered": ["string"],
  "styleVibeDescriptors": ["string"],
  "location": "string or object",
  "teamMemberNames": ["string"],
  "portfolioLinks": ["url"],
  "bookingContactLinks": ["url"],
  "testimonialsSocialProof": ["string or {quote,url}"],
  "valuesMissionStatement": "string",
  "rawPageText": "string",
  "sourceUrls": {
    "name": ["url"],
    "businessName": ["url"],
    "email": ["url"],
    "phone": ["url"],
    "socialHandles": { "instagram": ["url"], "twitter": ["url"], "...": ["url"] },
    "servicesOffered": ["url"],
    "styleVibeDescriptors": ["url"],
    "location": ["url"],
    "teamMemberNames": ["url"],
    "portfolioLinks": ["url"],
    "bookingContactLinks": ["url"],
    "testimonialsSocialProof": ["url"],
    "valuesMissionStatement": ["url"],
    "rawPageText": ["url"],
    "profileLink": ["url"]
  },
  "profileLink": "url"
}
```

**Empty fields** are allowed (empty string/array). **Each value** that exists **must carry its source URL(s)**.

---

## 5) Universal Configuration Principles

### 5.1 Route Targeting (S2 – Content Crawler)

* **Include (priority)**: `/about`, `/team`, `/people`, `/faculty`, `/staff`, `/leadership`, `/directory`, `/contact`, `/services`, `/book`, `/weddings`, `/events`, `/portfolio`, `/gallery`, `/publications`, `/artists`, `/performances`.
* **Deprioritize/Exclude**: blog archives, tag pages, search results, generic pagination without entity content.
* **Max Depth**: 2–3 (tunable by domain size).
* **Auto-pagination**: follow `rel=next` buttons; recognize `?page=`, `?start=`, numbered pagers.
* **Playwright**: enabled for JS-rich sites; configurable wait-for-selector for target sections.

### 5.2 Contact Extraction (S1 – Contact Scraper)

* **Stay within domain**; **max pages per domain** to cap costs.
* Capture **mailto/tel** and text-based matches (with “uncertain phone” suppressed or flagged).
* Normalize socials to canonical forms (e.g., `linkedin.com/in/...`, `instagram.com/...`).

### 5.3 AI Fallback (S3)

* Trigger **only when**:

  * No person names found, **or**
  * No email/phone/social found, **or**
  * Confidence score below threshold.
* Input: **raw HTML/text** + **URL**; Output: **schema JSON** + **sources** + **confidence**.
* Token bounds and defensive prompts to keep costs predictable.

---

## 6) Per-Domain State & Scoring (Stop Rules)

**DomainContext** (maintained in Make during merge/finalization):

* `domain`, `visitedUrls`, `leadsFound`, `score`, `threshold` (default: 10–12), `flags[]`.

**Score Weights (example defaults)**

* **Email** +5; **Phone** +3; **Name** +4; **BusinessName** +3;
* **Social handle** +2 each; **Profile page** +2; **Services** +3;
* **Location/address** +2; **Booking link** +2; **Portfolio** +2;
* **Testimonials** +2; **Mission/values** +2; **Team entries** +1 each.

**Stop Rule (conceptual)**

* When **score ≥ threshold** and **no high-priority routes remain**, halt further enqueueing for that domain to save time/cost.

---

## 7) Multi-Lead vs Single-Lead Handling

### 7.1 Single-Lead Sites (freelancers, small studios)

* Merge at **domain level**; prefer data from **/about** and **/contact**.
* Emit **one row** with best name + contact + context.

### 7.2 Multi-Lead Sites (faculty/staff/directories)

* Prefer person-specific **profile pages** → **key by `pageUrl`**.
* If directory is **inline only** (no profiles): **block-split** the page (div/li cards) and run **NER per block**.
* Emit **one row per person**; **profileLink** = profile URL, else directory URL.

---

## 8) Matching & Merging Keys (Integration Challenge)

**Key priority for merges**

1. `pageUrl` (profile pages)
2. `profileLink` (explicit links within directory blocks)
3. `email` (unique handle)
4. `name + domain` (with **fuzzy matching**, e.g., “A. Smith” ≈ “Alice Smith”)

**When individuals share a page**

* Use **block index** + **nearest email/phone** proximity within the block.
* If neither exists, match by **name tokens** and **role/title** cues (“Professor”, “Founder”).

**Field precedence**

* **Person-page data > team/directory page > homepage**.
* Don’t overwrite **strong contacts** (emails) with generic addresses.

---

## 9) Deduplication & Confidence

* **Person-level UID**: `profileLink`, else `email`, else `hash(name+domain)`.
* **Keep highest score** record when duplicates collide.
* **Emit `confidence`** (0–20) per lead; mark **low-confidence** (<10) for QA/fallback.

---

## 10) Pagination Strategy (Universal)

* Recognize `rel=next`, `.pagination a`, numeric page anchors, `?page=` or `?start=` patterns.
* Cap **max pages per domain** (e.g., 50) and **max requests** (e.g., 1,000) to avoid runaway crawls.
* Always **enqueue profile links** discovered on listing pages first (higher priority), then next list page.

---

## 11) NER & Context Extraction (No-Code/LLM)

**Name extraction**

* Run a **NER/LLM module** in Make over pageText or block-text to capture **full names** (with **role/title** if present).

**Context fields**

* **Services**: keyword lists per **CampaignMode** (wedding, corporate, mixed, universal).
* **Location**: look for **schema.org PostalAddress**, “City, ST”, office/room patterns.
* **Mission/values**: sentences near “our mission/we believe/my purpose”.
* **Style/Vibe**: LLM summarization of About/Portfolio language.
* **Booking/Portfolio/Testimonials links**: detect via URL patterns (`/book`, `/contact`, `/gallery`, `/portfolio`, `/publications`, `/testimonials|/reviews`).

**Attribution**

* For every extracted value, attach the **page URL(s)** that produced it into `sourceUrls`.

---

## 12) Google Sheets: Data Layout

**Staging Tabs**

* **Sheet A (Contact)**: `domain`, `pageUrl`, `emails[]`, `phones[]`, `socials[]`, `raw`.
* **Sheet B (Content)**: `domain`, `pageUrl`, `pageText`, `rawHTML`.
* **Sheet QA**: low confidence, missing essential fields, error logs.

**Final Leads**

* One row per **Lead** with all schema fields + `confidence` + `flags[]` + timestamps.

---

## 13) Make: Orchestration Scenarios (Modules & Logic)

**Scenario 1 – Harvest**

* Trigger on new Apify dataset items (S1 & S2).
* Normalize domains/URLs; write to **Sheet A/B**.

**Scenario 2 – Extract & Split**

* For **Sheet B** rows:

  * If **profile page** → send whole `pageText` to NER/LLM (names & roles).
  * If **listing/team page** → **HTML block split** → NER per block → emit multiple candidate people.

**Scenario 3 – Merge & Score**

* Join Sheet A & extracted people by keys (priority list).
* Compute **confidence score**; attach `sourceUrls`.
* **If score < threshold** → enqueue **AI fallback** for those URLs.
* Write **Final Leads** rows; mirror to **Apify Dataset (Merged)**.

**Scenario 4 – QA & Alerts**

* Nightly/weekly: build **QA report** (missing name/email, low confidence).
* Send Slack/email alerts with links to problem domains.
* Re-queue flagged items for fallback AI (S3) or future reruns.

**Scenario 5 – Scheduling & Scaling**

* Apify schedules for S1/S2.
* Make schedules for Scenarios 2–4.
* Throttle concurrency and batch sizes to control spend.

---

“13.5 – Email Validation (NeverBounce)” right after merging, so that only validated/clean emails flow into dedupe, scoring, and final output.

---

## 14) Automation Tactics (minimize manual work)

* **Standard route lists** & **pseudoURLs** (S2) that work across verticals.
* **Auto-pagination rules** (next buttons, query params).
* **Fuzzy matchers** (name+domain) to associate data without custom selectors.
* **Block splitting heuristics** for team/directory pages (div/li patterns).
* **LLM fallback** only for low-yield pages to keep costs low.
* **Weekly QA dashboard** that highlights only the exceptions.
* **Confidence-based stopping** to avoid over-crawling once a lead is “complete enough”.

---

## 15) CampaignMode (routing & vocabulary)

**Modes**: `wedding`, `corporate`, `mixed`, `universal`.
Each mode determines:

* **Route priority** (e.g., `wedding` → `/weddings|/elopement|/events`).
* **Service vocabulary** (keywords to collect).
* **Vibe/Style lexicon** (romantic, candid, editorial; or corporate/enterprise-grade).
* **Stop threshold** (e.g., `wedding` might demand Instagram + portfolio before halting).

---

## 16) Error Handling & Self-Healing

* **Retries**: transient failures rerun with backoff; switch proxy group if repeated.
* **JS timeouts**: Playwright waits for key selectors; if absent, downgrade to static content pass.
* **Obfuscation**: where supported by the actor, apply email decode; otherwise rely on **AI fallback**.
* **Robots & ethics**: respect robots.txt where appropriate; rate-limit to be good citizens.
* **Audit trail**: keep **run IDs**, **dataset IDs**, and **source URLs** per field.

---

## 17) Compliance & Risk

* **Public pages only**; no bypassing logins or paywalls.
* **GDPR/CCPA awareness**: treat personal contact data responsibly; provide removal processes.
* **LinkedIn**: do not scrape private member data; only normalize public URLs if exposed.
* **Opt-out**: maintain domain/URL blacklists.

---

## 18) Performance, Cost, and Scaling

* **Concurrency**: size the autoscaled pools per actor; use **Apify proxies**.
* **Caps**: `maxRequestsPerCrawl` and `maxPagesPerDomain`.
* **LLM budget**: fallback only for **low-confidence** or **missing essentials**; chunk text to **fit token limits**.
* **Caching**: cache already-processed domains to avoid re-crawling within SLA windows.

---

## 19) QA & Monitoring

* **KPIs**: domains processed, leads emitted, avg pages/lead, % leads with email/phone/social/name, avg confidence, cost/lead.
* **Dashboards**: Google Sheets pivot/tab + Make summary email/Slack.
* **Weekly sweep**: review “low confidence” and “missing name/email” buckets; re-queue specific URLs to **AI fallback**.

---

## 20) Roadmap (beyond MVP)

* **Entity linking**: associate leads across multiple domains (same person/site network).
* **Enrichment**: optional third-party APIs for missing emails/positions (respect TOS).
* **Learning loop**: store patterns from “fixed” sites to improve auto-routing/thresholds.
* **Multi-persona outreach**: auto-generate **MessagePersona** & **bestHookIdeas** per lead from captured context.
* **Notion/CRM sync**: direct inserts with de-dup gates.

---

## 21) Example Behaviors by Site Type

* **Faculty directory (deep pagination)**: S2 follows `?page=1..10`, extracts **profile links**; S1/S2 visit profiles; merge by **pageUrl**; emit one row per person with department (businessName), office location, publications as portfolio; `profileLink` = profile URL.
* **Freelance photographer**: S2 hits `/about|/contact|/portfolio|/book`; NER gets **name**, rules get **services** (wedding/elopement); S1 supplies **email/phone/socials**; LLM adds **vibe**; final row with source URLs.
* **Team page (no profiles)**: S2 pulls `/team` text; block-split into cards; NER per block yields multiple names; S1 provides any `mailto:` per block; create **multiple rows**, all sharing the same `pageUrl` but different block indexes.

---

## 22) Operational “Guardrails”

* **Threshold defaults**: 10–12 (stop when **email or phone** + **name** + **≥1 context** present).
* **Max depth**: 2 (3 for directory-heavy verticals).
* **Max pages/domain**: 50 (raise for universities).
* **Fallback trigger**: confidence <10 or missing **name** + **all contacts**.
* **Flags**: `LOW_CONFIDENCE`, `NO_EMAIL`, `NO_NAME`, `PAGINATION_FAIL`, `JS_RENDER_FAIL`.

---

## 23) What “Minimal Manual Work” Looks Like

* **Before run**: load domains; choose CampaignMode; press go.
* **During run**: no human action; Make coordinates merges and fallbacks.
* **After run**: check QA sheet; optionally re-queue a few flagged domains; export CSV/JSON.
* **Weekly**: skim dashboard; adjust thresholds only if metrics drift.

---

## 24) Final Notes

* You’re not betting everything on AI; you’re **layering AI only where deterministic methods fall short**.
* The system is **universal by design** (route lists, pseudoURLs, pagination rules, fuzzy matching) and **auditable** (per-field source URLs, dataset mirrors).
* You can **reach 90%+ effective automation** in your target verticals with this three-scraper stack, while preserving a clean path to a future, fully custom universal actor if/when you decide to build it.

---

**In short:** This specification delivers a **scalable, automated, and audit-friendly** contact/context pipeline using **Apify + Make + Google Sheets**, with **LLM fallback** for edge cases, **per-lead** JSON outputs, and **operational guardrails** that make it realistic to run at scale with **minimal manual work**.

**Reasoning**
I decomposed the build into sequential phases that mirror the data lifecycle: define schema/metrics → configure source scrapers (Apify actors) → stand up orchestration (Make) and staging stores (Sheets/Datasets) → perform NER/AI extraction and block-splitting → merge/match/score → validate emails → dedupe/finalize → QA/alerts → scheduling/scale → compliance → performance tuning → documentation. Each phase feeds the next (e.g., route patterns from Scraper 2 inform NER inputs; merged records precede NeverBounce; scoring precedes fallback AI and dedupe). Time estimates reflect your skills (Apify/Make experience, AI-assisted build) and bias toward automation over per-site tweaking.

---

**At a Glance Overview**

| Phase                         | Purpose                                                 | Est. Time                             |
| ----------------------------- | ------------------------------------------------------- | ------------------------------------- |
| 1. Scope & Data Model         | Lock schema, KPIs, campaign vocab, scoring              | 3.0 hrs                               |
| 2. Accounts & Environment     | Connect Apify, Make, Sheets, OpenAI, NeverBounce, Slack | 2.5 hrs                               |
| 3. Scraper 1 Config (Contact) | Emails/phones/socials extraction                        | 2.0 hrs                               |
| 4. Scraper 2 Config (Content) | Route-targeted crawl, pagination, text/HTML             | 3.0 hrs                               |
| 5. Orchestration & Staging    | Ingest datasets to Sheets; normalize                    | 3.0 hrs                               |
| 6. NER/AI & Block Splitting   | Names/roles from text; multi-person pages               | 5.0 hrs                               |
| 7. Merge, Matching, Scoring   | Join by keys; attribute sources; confidence             | 4.0 hrs                               |
| 8. Email Validation           | NeverBounce verify before dedupe                        | 1.0 hr                                |
| 9. Dedup & Finalization       | Unique leads to Final Sheet + merged Dataset            | 2.5 hrs                               |
| 10. QA & Exceptions           | Dashboards; requeue low-confidence                      | 2.5 hrs                               |
| 11. Scheduling & Monitoring   | Schedules, alerts, run logs                             | 2.0 hrs                               |
| 12. Compliance & Audit        | Robots, blacklists, retention                           | 1.0 hr                                |
| 13. Performance & Scale Test  | Concurrency/proxies; pilot tuning                       | 3.0 hrs                               |
| 14. Docs & Handoff            | README/runbook/troubleshooting                          | 2.0 hrs                               |
| **Total**                     |                                                         | **≈ 36.5 hrs (\~6 days @ 6 hrs/day)** |

---

**Phase 1: Scope & Data Model**
Purpose: Define what “good” looks like and how data will be structured and measured.

* **Step 1.1: Lead JSON schema & field-level source URLs**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Google Docs (spec), Google Sheets (schema tab).
  Integration: Drives mapping in Make; informs QA dashboard and final Sheet columns.

* **Step 1.2: Success metrics & thresholds**
  Est. Time: 0.5 hr • Difficulty: Easy
  Tools: Sheets (KPI tab).
  Integration: Used by QA (Phase 10) and Scoring (Phase 7).

* **Step 1.3: CampaignMode vocab (wedding/corporate/mixed/universal)**
  Est. Time: 1.0 hr • Difficulty: Medium
  Tools: Sheets (keywords tab).
  Integration: Guides services/vibe extraction and route priorities.

* **Step 1.4: Confidence scoring rubric**
  Est. Time: 0.5 hr • Difficulty: Medium
  Tools: Sheets (weights).
  Integration: Applied in Make during merge/scoring.

---

**Phase 2: Accounts & Environment**
Purpose: Wire all services for low-touch automation.

* **Step 2.1: Verify Apify actors**
  Est. Time: 0.5 hr • Difficulty: Easy
  Tools: Apify Console (vdrmota Contact, Web Content Crawler).
  Integration: Source scrapers.

* **Step 2.2: Connect Make, Sheets, OpenAI, NeverBounce, Slack**
  Est. Time: 1.5 hrs • Difficulty: Medium
  Tools: Make connections; Slack webhook.
  Integration: Orchestration, validation, alerting.

* **Step 2.3: Create Sheets templates (Staging A/B, Final, QA)**
  Est. Time: 0.5 hr • Difficulty: Easy
  Tools: Google Sheets.
  Integration: Landing zones and dashboards.

---

**Phase 3: Scraper 1 Config (Contact Info Scraper)**
Purpose: Extract emails, phones, socials at scale.

* **Step 3.1: Configure run (depth, proxy, stay-in-domain)**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Apify Console.
  Integration: Feeds Staging A.

* **Step 3.2: Pilot run & field mapping**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Apify Dataset viewer.
  Integration: Informs Make mappings.

---

**Phase 4: Scraper 2 Config (Website Content Crawler)**
Purpose: Route-aware crawl and pagination for names/context.

* **Step 4.1: Route targeting & pseudoURLs**
  Est. Time: 1.5 hrs • Difficulty: Medium
  Tools: Apify Console (include `/about|/team|/faculty|/people|/contact|/services|/book|/portfolio`).
  Integration: Feeds Staging B.

* **Step 4.2: Pagination rules & Playwright settings**
  Est. Time: 1.0 hr • Difficulty: Medium
  Tools: Apify (rel=next, numeric pagers; JS wait).
  Integration: Ensures full coverage.

* **Step 4.3: Sample run & content QA**
  Est. Time: 0.5 hr • Difficulty: Easy
  Tools: Dataset viewer.
  Integration: Validates text/HTML quality for NER.

---

**Phase 5: Orchestration & Staging**
Purpose: Move raw outputs into Sheets with normalization.

* **Step 5.1: Ingest S1 → Staging A**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Make (Apify → Sheets).
  Integration: Contact channels store.

* **Step 5.2: Ingest S2 → Staging B**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Make (Apify → Sheets).
  Integration: Text/HTML store.

* **Step 5.3: Normalize domains/URLs/socials**
  Est. Time: 1.0 hr • Difficulty: Medium
  Tools: Make (Routers/Formatters).
  Integration: Consistent keys for joining.

---

**Phase 6: NER/AI & Block Splitting**
Purpose: Extract names/roles; handle multi-person pages.

* **Step 6.1: Block segmentation (cards/lists)**
  Est. Time: 1.5 hrs • Difficulty: Medium
  Tools: Make (HTML parser/Iterator).
  Integration: One row per person candidate from a single URL.

* **Step 6.2: NER/LLM extraction**
  Est. Time: 2.0 hrs • Difficulty: Medium
  Tools: Make + OpenAI (prompt for name, role, mission, services, location).
  Integration: Produces people\_by\_page with provenance.

* **Step 6.3: Persist people\_by\_page**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Sheets (Staging People).
  Integration: Join table for Merge.

* **Step 6.4: Cost guardrails**
  Est. Time: 0.5 hr • Difficulty: Easy
  Tools: Make (batching, token caps, rate limits).
  Integration: Keeps AI costs predictable.

---

**Phase 7: Merge, Matching, Scoring**
Purpose: Build unified lead objects with confidence.

* **Step 7.1: Join logic (pageUrl → profileLink → email → fuzzy name+domain)**
  Est. Time: 2.0 hrs • Difficulty: Hard
  Tools: Make (Routers, Filters, Fuzzy matching module/logic).
  Integration: Core consolidation.

* **Step 7.2: Source URL attribution aggregator**
  Est. Time: 1.0 hr • Difficulty: Medium
  Tools: Make (Array aggregators).
  Integration: Field-level provenance.

* **Step 7.3: Confidence scoring**
  Est. Time: 1.0 hr • Difficulty: Medium
  Tools: Make (formula weights per field).
  Integration: Drives fallback and QA.

---

**Phase 8: Email Validation (NeverBounce)**
Purpose: Verify emails before dedupe.

* **Step 8.1: Validate emails, map statuses**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Make (HTTP module → NeverBounce API).
  Integration: Append status/score to lead; mark unreachables.

---

**Phase 9: Dedup & Finalization**
Purpose: One row per person with best data.

* **Step 9.1: UID strategy & dedupe**
  Est. Time: 1.5 hrs • Difficulty: Medium
  Tools: Make (Set/Map ops).
  Integration: UID by profileLink → email → hash(name+domain).

* **Step 9.2: Write Final Leads + Apify merged Dataset**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Make (Sheets writer; Apify dataset writer).
  Integration: Canonical outputs.

---

**Phase 10: QA & Exceptions**
Purpose: Visibility and automated remediation.

* **Step 10.1: QA dashboards (coverage, completeness, confidence)**
  Est. Time: 1.5 hrs • Difficulty: Medium
  Tools: Sheets (pivots/conditional formatting).
  Integration: Ops view.

* **Step 10.2: Exception queues & reprocessing**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Make (filters to AI fallback or rerun flags).
  Integration: Self-healing loop.

---

**Phase 11: Scheduling & Monitoring**
Purpose: Hands-off operation.

* **Step 11.1: Apify schedules for S1/S2; Make schedules for flows**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Apify schedules; Make scheduler.
  Integration: Periodic runs.

* **Step 11.2: Alerts & run logs**
  Est. Time: 1.0 hr • Difficulty: Medium
  Tools: Make → Slack/Email; store run IDs/metrics.
  Integration: On-call visibility.

---

**Phase 12: Compliance & Audit**
Purpose: Responsible, auditable scraping.

* **Step 12.1: Robots/blacklists/opt-out**
  Est. Time: 0.5 hr • Difficulty: Easy
  Tools: Sheets (blacklist), Apify settings.
  Integration: Respectful crawling.

* **Step 12.2: Data retention & PII notes**
  Est. Time: 0.5 hr • Difficulty: Easy
  Tools: Sheets (retention policy), Make (purge routines).
  Integration: Cleanup and compliance.

---

**Phase 13: Performance & Scale Test**
Purpose: Tune for throughput and cost.

* **Step 13.1: Concurrency, proxies, caps**
  Est. Time: 1.5 hrs • Difficulty: Medium
  Tools: Apify (autoscaled pool, proxy groups; max pages/domain).
  Integration: Reliable scale.

* **Step 13.2: Pilot on 50 domains; adjust thresholds**
  Est. Time: 1.5 hrs • Difficulty: Medium
  Tools: Sheets KPIs; Make logs.
  Integration: Data-driven tuning.

---

**Phase 14: Documentation & Handoff**
Purpose: Operational clarity.

* **Step 14.1: README & runbook**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Docs/Notion.
  Integration: How-to and SOPs.

* **Step 14.2: Troubleshooting guide**
  Est. Time: 1.0 hr • Difficulty: Easy
  Tools: Docs/Notion.
  Integration: Faster recovery.

---

**Total Estimated Project Duration:** ≈ 36.5 hours (\~6 days at 6 hrs/day)

**Integration Notes / Caveats**

* Place **NeverBounce** immediately after merge/scoring and before dedupe to avoid propagating bad emails.
* Keep **AI fallback** conditional on confidence to manage token spend.
* Favor **pageUrl** as primary join key; fall back to **profileLink → email → fuzzy name+domain**.
* Use **Playwright** in Scraper 2 for JS-heavy sites; cap depth/pages to avoid runaway crawls.
* Weekly QA should target only low-confidence/missing-essential rows to preserve low manual overhead.


# Context Summary

**Scraper 2: Website Content Crawler (from OUS 3SS)** — distilled:

* **Goal:** Given a seed (often a directory/roster page), crawl *just enough* to reach **profile pages** and extract **lead-like fields** plus **AI-ready page content**.
* **Core outputs:**

  * Page-level: `url`, `markdown`, `html?`, `metadata`, `status`, `screenshots?`
  * Lead-level (per profile, when present): `name`, `title/role`, `email`, `phone?`, `org`, `profile_url`, `raw_page_text`, and **`sourceUrls` per field** (traceability).
* **Crawl behavior:**

  * Config-driven **selectors** for list/roster pages (profile link selectors, pagination selectors).
  * **Depth-2** crawl (list → profile) with dedupe, canonicalization, include/exclude patterns, and **robots.txt** compliance.
  * **Politeness** (concurrency caps, jitter delays, retries).
* **Interface & modes:**

  * REST API (FastAPI) with `/crawl` accepting: `url`, `max_depth` (usually 1–2), `max_pages`, `include_patterns`, `exclude_patterns`, `respect_robots_txt`, **`campaign`** (loads per-site/per-vertical selector packs).
  * **Optional JSONL streaming** for large result sets.
  * **Optional LLM fallback** when deterministic extractors miss fields.
* **Quality & ops:**

  * **Config over code** for site-specific CSS/XPath selectors.
  * **Field-level provenance** via `sourceUrls`.
  * Minimal, testable units (`parse_list_page`, `parse_profile_page`) and light metrics/health.

# Comparison Table

| Requirement (Scraper 2)                                                  |     Is Covered | Notes                                                                                           |
| ------------------------------------------------------------------------ | -------------: | ----------------------------------------------------------------------------------------------- |
| FastAPI app with /crawl endpoint                                         |        **Yes** | eGet exposes `crawler` router under `/api/v1` (routers are included in `main.py`).              |
| /scrape endpoint for single page                                         |        **Yes** | Present and building `options` (wait-for selector, screenshot, headers).                        |
| Chunker & converter endpoints                                            |        **Yes** | Routers included in app.                                                                        |
| Selenium/Playwright rendering                                            |        **Yes** | Framework stack + options already present (per README you shared).                              |
| Robots.txt compliance                                                    |        **Yes** | Listed as a feature in the README you provided.                                                 |
| Config-driven selectors (YAML) for list/profile pages                    |    **Partial** | eGet has `link_extractor`, but not a YAML “campaign” map for selectors by vertical/site.        |
| Pagination on list/roster pages                                          |    **Partial** | Generic link discovery exists; explicit next/prev selector handling needs config + queue logic. |
| Depth-2 crawl (list → profile)                                           |    **Partial** | Link discoverer exists; needs targeted **profile link** selectors and controlled enqueueing.    |
| Dedup & canonicalization                                                 |    **Partial** | Likely present at queue level; needs explicit canonicalize + `seen` set for robustness.         |
| Include/exclude patterns                                                 |        **Yes** | Supported by existing crawler request models per README; ensure wired into service.             |
| Politeness (concurrency, jitter, retries)                                |        **Yes** | Concurrency caps and retries exist; add jitter delay if not already tuned.                      |
| Output: AI-ready markdown + metadata                                     |        **Yes** | Built-in markdown conversion & metadata in current eGet.                                        |
| **Lead model** (name, title, email, phone, org, profile\_url, raw\_text) |    **Partial** | Current output focuses on page content; **needs Lead Pydantic model** and profile parsing.      |
| **sourceUrls per field**                                                 |         **No** | Needs explicit field-to-url mapping (typically the profile URL).                                |
| JSONL streaming results                                                  | **No/Partial** | Current responses appear array-based; add optional JSONL stream for large crawls.               |
| Request param **campaign** to load selectors                             |         **No** | Add `campaign` to `/crawl` request and load YAML selector pack accordingly.                     |
| Optional LLM fallback                                                    |    **Partial** | The stack supports LLMs; add gated fallback path only when structured parse fails.              |
| Tests for list/profile parsers                                           |         **No** | Add minimal pytest fixtures for roster and profile HTML.                                        |
| Field validation (emails, names)                                         |    **Partial** | Some validators exist; extend for lead fields.                                                  |
| Field/URL provenance logging                                             |    **Partial** | General logging exists; add counters for “profiles found / leads extracted / missing fields”.   |
| Metrics/health                                                           |        **Yes** | `/metrics`, `/health` present.                                                                  |

# Change Proposals

> Design principle: **Minimal, config-driven additions** that reuse eGet’s crawler, scraper, and API, while adding a small, well-scoped Lead extractor layer.

---

## 1) Add **campaign-driven selectors** (YAML)

**Reasoning:** Scraper 2 requires per-vertical/per-site selector packs for **list pages** (profile links + pagination) and basic **profile parsing hooks**. Keeping selectors in YAML avoids code churn and speeds iteration.

**Recommended minimal updates:**

* **Add** `configs/selectors.yaml`:

  * `campaign` → `{ list_link_selectors: [...], next_page_selectors: [...], profile_page_hints: [...], profile_field_selectors: { name: [...], title: [...], email: [...], phone: [...] } }`
* **Add** a tiny loader: `services/crawler/config_loader.py` that returns a `SelectorPack` for a `campaign` string.
* **Wire** `campaign` into `/api/v1/crawl` request model and service call.

*Patch outline:*

* `models/crawler_request.py`: add `campaign: Optional[str] = None`.
* `api/v1/endpoints/crawler.py`: pass `campaign` to `CrawlerService.crawl(...)`.
* `services/crawler/crawler_service.py`: load `SelectorPack = config_loader.load(campaign)`; use `list_link_selectors` to enqueue **profile URLs**, use `next_page_selectors` to enqueue **next** pages; restrict depth to **2** by default.

---

## 2) Implement **Depth-2 list → profile** crawl

**Reasoning:** Requirement targets list/roster → profile traversal, not site-wide spidering.

**Recommended minimal updates:**

* In `crawler_service.py`:

  * When `depth == 0` on list pages, **extract profile links** via `SelectorPack.list_link_selectors`; `enqueue(profile_url, depth=1)`.
  * Extract `next` via `SelectorPack.next_page_selectors` with same depth.
  * At `depth == 1`, treat as **profile pages**; push to the **Lead extractor** (below).
* Add a `canonicalize_url(url)` util and a `seen_urls` set to prevent duplicates.

---

## 3) Create a light **Lead** model and **Profile extractor**

**Reasoning:** Scraper 2 requires **lead-like fields** and **sourceUrls per field**; this is not in eGet’s default page-content outputs.

**Recommended minimal updates:**

* **Add** `models/lead.py` (Pydantic):

  * `name`, `title`, `email`, `phone`, `org`, `profile_url`, `raw_page_text`, `sourceUrls: Dict[str, str]`
* **Add** `services/extractors/profile_extractor.py`:

  * `parse_profile_page(html, url, selector_pack) -> Optional[Lead]`

    * Try CSS selectors from `selector_pack.profile_field_selectors`
    * For `email`: prefer `mailto:`, fallback regex; normalize; set `sourceUrls['email'] = url` (or the subelement’s href if available).
    * Always set `profile_url = url`, `sourceUrls[field] = url` for every extracted field.
    * `raw_page_text` from cleaned text (cap length).
* In `crawler_service.py` at `depth == 1`, call the extractor; append leads to a `leads` list in the crawl result.

---

## 4) Extend **crawl response** to include leads (+ optional JSONL)

**Reasoning:** Scraper 2 wants both page documents and extracted leads; large crawls may benefit from streaming.

**Recommended minimal updates:**

* **Add** a `models/crawler_response.py` field `leads: List[Lead] = []`.
* **Optional streaming:** in `api/v1/endpoints/crawler.py`, add `stream=true` query param; when set, return `StreamingResponse` yielding **JSON Lines** of `{type: "page"|"lead", data: {...}}`.
* Keep the default (non-stream) behavior as today for backward compatibility.

---

## 5) Add **campaign** to the API request and wire it through

**Reasoning:** Requirement calls for selector packs by vertical/site.

**Recommended minimal updates:**

* `models/crawler_request.py`: `campaign: Optional[str]`
* `api/v1/endpoints/crawler.py`: document it in OpenAPI and pass to service
* `crawler_service.py`: pass to `config_loader`, default to “universal” if `None`

---

## 6) **Pagination** on list pages

**Reasoning:** Roster pages often paginate; selectors must be used to enqueue next pages safely.

**Recommended minimal updates:**

* Use `SelectorPack.next_page_selectors` to find **single** next link; enqueue with same `depth=0`.
* Guard against infinite loops via `seen_urls` and **max\_pages**.

---

## 7) **Politeness tuning** (jitter)

**Reasoning:** Politeness already exists; minor improvement.

**Recommended minimal updates:**

* Add a small **random jitter** (e.g., 300–1500ms) between navigation events within a host. Make it configurable in `settings`.

---

## 8) **Field validators** for lead extraction

**Reasoning:** Improve correctness and avoid garbage data.

**Recommended minimal updates:**

* `services/extractors/validators.py`:

  * `is_plausible_name`, `normalize_title`, `normalize_email(domain_hint)`, `normalize_phone`.
* Use these in `profile_extractor.py` before returning a Lead.

---

## 9) **LLM fallback** (optional/gated)

**Reasoning:** For hard pages, allow optional fallback; keep it **off by default**.

**Recommended minimal updates:**

* In `profile_extractor.py`, if selectors fail and `use_llm_fallback` is `True`:

  * Call `llm_extract(html, prompt)` returning the same `Lead` schema; set `sourceUrls[field] = profile_url`.
* Feature-flag via request or settings; add simple budget/timeouts.

---

## 10) **Minimal tests** for list/profile parsing

**Reasoning:** Prevent regressions; keep very light.

**Recommended minimal updates:**

* `tests/fixtures/roster.html`, `tests/fixtures/profile.html`
* `test_profile_extractor.py`: asserts that `parse_profile_page()` extracts a plausible lead and populates `sourceUrls`.
* `test_list_links.py`: asserts that roster → expected profile URLs.

---

## 11) **Telemetry counters** (optional)

**Reasoning:** Useful for QA of Scraper 2 output.

**Recommended minimal updates:**

* Increment simple counters: `profiles_found`, `leads_parsed`, `leads_missing_email`. Expose in `/metrics`.

---

# Conclusion

**Readiness:** The base eGet app already provides **80%** of Scraper 2: FastAPI structure, crawler & scraper endpoints, rendering, robots, chunker/converter, metrics/health (routers are included and live).  The remaining **20%** is focused, minimal, and configuration-driven:

* Add **campaign selectors (YAML)** + tiny loader
* Implement **Depth-2 list→profile** traversal with pagination and dedupe
* Introduce a light **Lead** model + **profile extractor**
* Attach **sourceUrls per field**
* Optional **JSONL streaming** and **LLM fallback**

These changes are small, elegant, and keep eGet’s architecture intact while fully meeting Scraper 2. Next step: I can draft the exact `selectors.yaml`, `Lead` model, and `profile_extractor.py` scaffolds tailored for your first campaign (e.g., *university\_faculty*) and a short PR plan to land them cleanly.


TL;DR
You can extend the existing eGet Website Crawler (Scraper 2) so that it does everything the 3‑SS design calls for – names, emails, socials, pagination, profile‑page discovery, and per‑lead coordination. It will require a modest amount of engineering (roughly 2 – 3 working days for a solid MVP) because the bulk of the heavy lifting (HTTP fetching, Playwright rendering, politeness, robots‑txt handling) is already in place.

Below is a step‑by‑step roadmap, the why behind each change, and a time‑box estimate. I also point out where you might still want to keep a dedicated “Contact‑Info Scraper” (your current open‑source Scraper 1) as a fallback for especially noisy sites.

1️⃣ High‑level architectural decision
Option	What you keep	What you add / modify	Pros	Cons
A – Extend eGet only	Use eGet as the sole crawler for both profile‑content and contact fields.	Add selector‑driven name/email/social extraction, depth‑2 list → profile logic, lead‑coordination, optional AI fallback.	One codebase, single deployment, easier orchestration, consistent provenance (sourceUrls).	Slightly larger surface area; you still may want a lightweight “quick‑email” scraper for ultra‑fast single‑page sites.
B – Keep 3‑SS as‑is	Keep Scraper 1 (pre‑built contact scraper) + Scraper 2 (eGet) + Scraper 3 (AI).	Only glue code to merge results downstream.	Proven contact‑scraper already tuned for email/phone extraction; less risk of breaking it.	Two actors to maintain, duplicated crawling of the same pages (extra cost, extra latency).
Recommendation	Start with Option A (extend eGet) and keep Scraper 1 as a fallback that you can disable for sites where eGet succeeds. This gives you the “single‑actor” simplicity while preserving a safety net for the hardest cases.			
2️⃣ Concrete changes to eGet (the “Website Content Crawler”)
Below each change I note what file/module you’ll likely touch, why it matters, and a rough effort.

2.1 Add a campaign‑driven selector model
File(s): configs/selectors.yaml (new) + services/crawler/config_loader.py (new).
What it does: Stores, per campaign (e.g., faculty_directory, photographer_portfolio, generic_business), the CSS/XPath selectors for:
List‑page link selectors (how to find profile URLs on a roster page).
Pagination selectors (rel=next, .pager a, ?page= patterns).
Profile‑page field selectors for name, email, phone, socials, title, organization, etc.
Why: Keeps the crawler data‑driven; you can add a new vertical without touching Python code.
Effort: 2 h to draft the YAML schema and a tiny loader that returns a CampaignConfig object.
2.2 Create a Lead model with provenance
File(s): models/lead.py (new).
What it does: Mirrors the JSON schema you posted (name, email, socials, services, sourceUrls, profileLink, etc.). Each field is a Optional[...] plus a parallel sourceUrls dict that records the page(s) that yielded the value.
Why: Guarantees field‑level source URLs (a core requirement of the 3‑SS spec) and makes downstream merging trivial.
Effort: 1 h (Pydantic model + dict helpers for adding provenance).
2.3 Implement profile‑page extraction (profile_extractor.py)
File(s): services/crawler/profile_extractor.py (new).
What it does:
Receives a profile URL + the CampaignConfig.
Fetches the page (via existing Playwright/requests wrapper).
Runs the field selectors, populates a Lead instance, and records each selector’s source URL.
Falls back to regex‑based email/phone detection if a selector is missing (covers sites that hide contact info in plain text).
Why: Centralises all deterministic extraction in one place; makes it easy to unit‑test.
Effort: 3 h (selector application, regex fallback, unit tests).
2.4 Add depth‑2 crawl orchestration (crawler_service.py)
File(s): services/crawler/crawler_service.py (modify).
What it does:
Starts from the seed URL (the directory or homepage).
Uses the list‑page selectors to collect profile URLs.
Applies pagination selectors until max_pages or max_requests limits are hit.
De‑duplicates URLs (canonicalization).
Calls profile_extractor for each discovered profile URL (concurrently, respecting the existing concurrency caps).
Returns a list of Lead objects plus any “orphan” leads that were found on a list page without a dedicated profile (block‑split fallback – see 2.6).
Why: This is the core “list → profile” flow the 3‑SS spec demands.
Effort: 4 h (queue handling, pagination loop, concurrency, error handling).
2.5 Expose the campaign parameter in the API request model
File(s): models/crawler_request.py (add campaign: str = "generic").
File(s): main.py (FastAPI) – update /crawl endpoint to accept the new field and pass it to CrawlerService.
Why: Allows you to pick the right selector set at runtime (e.g., campaign="faculty").
Effort: 30 min.
2.6 Add block‑splitting for list pages that lack individual profile links
File(s): services/crawler/block_splitter.py (new).
What it does:
Parses the HTML of a list page, looks for repeating card‑like containers (<div class="card">, <li>, etc.).
Runs the same NER/email regexes on each block’s text to generate multiple Lead objects that share the same pageUrl but have distinct sourceUrls.
Why: Faculty directories often embed several people on a single page without separate URLs.
Effort: 2 h (simple heuristic + unit test).
2.7 Add optional AI fallback hook (Scraper 3)
File(s): services/fallback_ai.py (new, thin wrapper).
What it does:
Receives a Lead with missing high‑priority fields (name, email, at least one contact).
Calls your chosen LLM endpoint (OpenAI, Anthropic, etc.) with a deterministic prompt that asks for the JSON schema plus source URLs (you can reuse the prompt you already have for Scraper 3).
Merges the AI‑generated fields back into the Lead.
Why: Keeps the “edge‑case” capability inside the same actor, so you can run a single‑pass pipeline when you want (e.g., for a quick proof‑of‑concept).
Effort: 2 h (prompt design, API wrapper, rate‑limit handling).
2.8 Update output format (JSON Lines + optional markdown)
File(s): models/crawler_response.py (extend with leads: List[Lead]).
File(s): run.py (Apify actor) – after the crawl finishes, push the list of leads to the Apify dataset (or stream as JSON‑Lines).
Why: Matches the schema you posted and makes downstream merging trivial.
Effort: 1 h.
2.9 Write minimal pytest suite
Tests:
List‑page pagination & profile‑URL discovery.
Profile extraction for a sample page (assert name/email/socials + sourceUrls).
Block‑split fallback on a mock multi‑lead list page.
AI fallback stub (mocked LLM response).
Why: Guarantees that each new piece works in isolation and prevents regressions when you later tweak selectors.
Effort: 2 h.
2.10 Documentation & sample campaign YAML
File: configs/selectors.yaml – include at least three starter campaigns (faculty, photographer, generic).
README section describing how to add a new campaign.
Effort: 1 h.
3️⃣ Time‑boxed roadmap (full MVP)
Day	Tasks (approx.)	Cumulative hrs
Day 0	Set up a branch, run existing eGet tests, confirm baseline works.	1
Day 1	1️⃣ Selector model + config loader (2 h) 2️⃣ Lead model (1 h) 3️⃣ Profile extractor (3 h)	6
Day 2	4️⃣ Depth‑2 crawl orchestration (4 h) 5️⃣ API request update (0.5 h) 6️⃣ Block‑splitter (2 h)	12.5
Day 3	7️⃣ AI fallback wrapper (2 h) 8️⃣ Output response & Apify dataset push (1 h) 9️⃣ Pytest suite (2 h) 10️⃣ Docs & sample YAML (1 h)	18.5
Buffer	Bug‑fixes, logging polish, CI integration	~2 h
Total	≈ 20 hours (~2½ working days)	
If you want a leaner version (skip AI fallback and block‑split for now) you can shave ~4 h, bringing the MVP down to ~16 h.

4️⃣ Where to keep Scraper 1 (the pre‑built contact scraper)
Even after extending eGet, there are two scenarios where the original contact‑scraper remains valuable:

Situation	Why keep it
Ultra‑fast single‑page sites (e.g., a photographer’s landing page with a visible mailto:)	The contact scraper can pull the email in < 100 ms without launching the full depth‑2 crawl.
Sites that deliberately hide contact info behind JavaScript that eGet’s Playwright rendering struggles with (heavy SPA, Cloudflare challenges)	The open‑source scraper you already have may have custom anti‑bot tricks or a different headless engine that succeeds where eGet times out.
Cost‑control	Running the cheap contact scraper first, then falling back to the heavier eGet only when it reports “no leads found”, reduces overall compute spend.
Implementation tip: In the Apify actor’s run.py, call the contact scraper first; if it returns ≥ 1 lead with a valid email/phone, skip the depth‑2 crawl for that domain. Otherwise, invoke the extended eGet pipeline.

5️⃣ How the extended eGet fits the 3‑SS “ideal output”
Field (from your JSON schema)	Source after extension
name, title/role, businessName	Extracted by profile selectors or NER on block text.
email, phone, socialHandles.*	Regex fallback + selector‑driven extraction on profile pages.
servicesOffered, styleVibeDescriptors, location, valuesMissionStatement, portfolioLinks, bookingContactLinks, testimonialsSocialProof	Same as before – eGet already returns raw page text; you add deterministic regex/keyword selectors for the most common patterns.
rawPageText	Already provided by eGet (markdown/html).
sourceUrls (per field)	New – every extraction routine records the URL that produced the value.
profileLink	The URL of the profile page (or the list‑page URL when block‑splitting).
confidence (optional)	Simple scoring: +5 for email, +4 for name, +2 per social, +3 for services, etc. (you can add this later).
Thus the single‑actor eGet‑extended pipeline can deliver exactly the JSON you described, with the same granularity and provenance that the 3‑SS spec requires.

6️⃣ Quick checklist for you before you start
Clone the eGet repo on a fresh branch.
Verify you can run the existing FastAPI /crawl endpoint locally.
Install pydantic, pytest, and any missing dev deps.
Create a configs/ folder (git‑ignore the YAML if you want to keep it secret).
Draft the first campaign (generic) with a few universal selectors:
generic:
  list_selectors:
    - "a[href*='/team/'], a[href*='/people/']"
  pagination_selectors:
    - "a[rel='next']"
    - "a.next"
  profile_fields:
    name: "h1, .person-name"
    email: "a[href^='mailto:']"
    phone: "a[href^='tel:'], .phone"
    socials:
      instagram: "a[href*='instagram.com']"
      twitter: "a[href*='twitter.com']"
      linkedin: "a[href*='linkedin.com']"
Run the unit tests after each major change; they’ll catch selector‑lookup errors early.
7️⃣ Bottom line
Yes – eGet can be turned into the “universal” scraper you need.
The work is mostly additive (selectors, a Lead model, depth‑2 orchestration) and fits cleanly into the existing codebase.
Estimated effort: ~20 hours for a production‑ready MVP that covers pagination, profile discovery, multi‑lead pages, and per‑field source URLs.
Recommended workflow: Extend eGet as described, keep your current contact‑scraper as a cheap first‑pass fallback, and optionally invoke the AI fallback only when the deterministic pipeline fails to meet the confidence threshold.
Let me know which part you’d like to dive into first (e.g., the selector YAML design, the profile‑extractor implementation, or wiring the depth‑2 crawl), and I can provide a concrete code snippet to get you started!


4 files