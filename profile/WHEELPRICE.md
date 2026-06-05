# WheelPrice — Complete Interview Reference

---

## Index

1. [Who They Are and What I Did There](#1-who-they-are-and-what-i-did-there)
2. [Why I Left](#2-why-i-left)
3. [Project 1 — CMS Blog Subsystem](#3-project-1--cms-blog-subsystem)
4. [Project 2 — Agentic Fitment Assistant](#4-project-2--agentic-fitment-assistant)
5. [Project 3 — Churn and User Behavior Dashboard](#5-project-3--churn-and-user-behavior-dashboard)
6. [Project 4 — Fitment Visualizer (Computer Vision)](#6-project-4--fitment-visualizer-computer-vision)
7. [Cross-Cutting Technical Concepts](#7-cross-cutting-technical-concepts)
8. [General WheelPrice Follow-Up Questions](#8-general-wheelPrice-follow-up-questions)

---

## 1. Who They Are and What I Did There

WheelPrice is a Techstars-backed marketplace for automotive wheels and parts. The core product is a third-party marketplace API — buyers search for wheels, check fitment compatibility, and purchase. The team was small — two engineers total — with no dedicated DevOps.

I joined as an AI Engineer and ended up owning the full stack across four distinct initiatives: content infrastructure, an AI fitment assistant, an internal analytics dashboard, and a computer vision fitment visualizer. Because the team was so small, I wasn't handed tickets — I identified problems, proposed solutions, and owned them end-to-end from architecture through deployment.

**The one-line answer to "what did you do there":**

"I built the data and AI layer at WheelPrice — content infrastructure that drove organic growth, an agentic assistant that automated fitment support, and an internal analytics system that made user behavior legible to the team for the first time."

---

## 2. Why I Left

Honest, clean answer — no negativity:

"WheelPrice was a great environment to move fast and own a lot. I learned an enormous amount building across the full stack with real constraints. I'm leaving because I want to go deeper on the systems side — the work I find most interesting is at the infrastructure and AI engineering layer, and I want to be in an environment where that's the core focus rather than one of many hats. The research I've been doing in parallel — MetaRAG and TeamMedAgents — reflects where I want to go, and I'm looking for a role where that kind of technical depth is the expectation, not the exception."

---

## 3. Project 1 — CMS Blog Subsystem

### The Story

WheelPrice had a large social following but zero organic search presence. No blog, no SEO surface area, no reason for Google to index the site beyond the product pages. Traffic from social was landing on the platform but not converting — there was no content layer to capture it.

I proposed and built a complete blog CMS from scratch. The core design decision was whether to bolt it onto the existing codebase or build it as an independent service. The existing platform ran on a third-party marketplace API I couldn't touch — any tight integration would mean their release cycle blocked my ability to ship. I built it as an independent Node.js/React/TypeScript microservice under the same domain but with its own MongoDB collections and build pipeline. Same stack as the rest of the product, completely decoupled in deployment.

What I built on the content side: rich text editor with image optimization pipeline, tag and category taxonomy, author management, slug-based routing with canonical URLs. On the SEO side: dynamic sitemap generation, Open Graph metadata per post, Article schema structured data, and server-side rendering so crawlers could read actual content rather than a JavaScript shell.

The non-technical piece mattered as much as the technical one. I built automated ingestion hooks so non-technical team members could publish from familiar tools and have content land with SEO fields pre-populated. Removed the engineer bottleneck from every post.

First version had no caching. Under load spikes — when a social post went viral and redirected traffic — server-side rendering every request against MongoDB tanked response times. I added Redis caching for rendered pages with tag-based cache invalidation on content updates. That stabilized it.

Result: daily viewership increased to 10-20k. The bulk came from organic search picking up long-tail automotive fitment queries the social content was already ranking for — we just had no landing page to capture the traffic. After launch, those queries resolved to the blog.

---

### Follow-Up Questions and Answers

**Why build a custom CMS instead of WordPress or a headless CMS like Contentful?**

Two constraints drove this. First, the team was two engineers with no DevOps — introducing a separate CMS runtime meant two systems to maintain, two deployment targets, two sets of credentials and monitoring. A custom build meant one codebase, one pipeline. Second, the content model needed to be automotive-specific — fitment tags, vehicle make/model/year taxonomies, structured data tied to product SKUs. WordPress's generic content model would have needed heavy customization anyway. Building custom meant I could tailor the schema exactly to what we needed without fighting the tool.

**What is server-side rendering and why does it matter for SEO?**

A standard React app ships an HTML file with a mostly empty body and a JavaScript bundle. The browser downloads the JS, executes it, and then the content appears. Google's crawler can execute JavaScript, but it's unreliable — it may index the page before JS runs, or deprioritize pages that require JS to render content.

Server-side rendering means the server executes React and sends fully-formed HTML to the browser. When Google's crawler hits the URL, it gets actual content immediately — no JS dependency. The page is indexable from the first byte. For a content-heavy blog where ranking on Google is the entire point, SSR is not optional.

**What is a dynamic sitemap and why does it exist?**

A sitemap is an XML file at `/sitemap.xml` that tells search engines "here are all the URLs on this site, and here's when each was last updated." Without one, Google discovers pages by following links — slow and incomplete. With one, you're explicitly telling Google every page that exists.

Dynamic means the sitemap is generated on request rather than being a static file. Every time a new post is published, the sitemap includes it automatically — no manual update, no deployment required. A static sitemap goes stale the moment you publish new content.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://wheeliprice.com/blog/best-wheels-honda-civic</loc>
    <lastmod>2024-01-15</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  ...
</urlset>
```

The endpoint queries MongoDB for all published posts and generates this XML on the fly. Google re-crawls it periodically and discovers new content within hours of publication.

**What is Open Graph metadata?**

HTML meta tags in the `<head>` that control how a page appears when shared on social platforms — Facebook, Twitter, LinkedIn, Slack all read these.

```html
<meta property="og:title" content="Best Wheels for Honda Civic 2022" />
<meta property="og:description" content="Complete fitment guide..." />
<meta property="og:image" content="https://wheeliprice.com/og/civic-wheels.jpg" />
<meta property="og:url" content="https://wheeliprice.com/blog/best-wheels-honda-civic" />
```

Without these, social platforms generate a preview from whatever text they find first — usually ugly and off-brand. With them, every shared link shows a clean image, title, and description. Directly affects click-through rate on social shares.

**What is Article schema / structured data?**

JSON-LD markup embedded in the page that tells Google "this is an article, it was written by this author, published on this date, about this topic." Google uses it to generate rich results — the card-style search results with author photos, dates, and star ratings.

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "Best Wheels for Honda Civic 2022",
  "author": {"@type": "Person", "name": "Pranav Mishra"},
  "datePublished": "2024-01-15",
  "publisher": {"@type": "Organization", "name": "WheelPrice"}
}
</script>
```

**What is tag-based cache invalidation and why not just TTL?**

TTL (time-to-live) expiration says "this cache entry expires after N seconds." The problem: if you publish a new post, the sitemap cache still serves the old version for up to N seconds. For SEO, you want Google to see the new post immediately.

Tag-based invalidation means every cached item is tagged with what data it depends on. When that data changes, all related caches are invalidated atomically.

```
POST /api/posts (publish new post)
  → invalidate cache entries tagged ["sitemap", "post-list", "tag:wheels", "category:honda"]
  → next request regenerates only the affected pages
```

TTL is simpler but produces stale content. Tag invalidation is more complex but keeps cache consistent with data at all times.

**What is a microservice and why did it matter here?**

A microservice is an independently deployable service with its own data store, deployment pipeline, and runtime. The alternative is a monolith — one codebase, one deployment.

The reason it mattered: the core WheelPrice platform ran on a third-party marketplace API. That vendor pushes updates on their own schedule. If my blog code was tightly integrated, their updates could break my routes, my schemas, my build. Decoupled as a separate service, I could deploy the blog independently, update it without touching the marketplace code, and absorb vendor changes without it cascading.

The trade-off: two services to monitor instead of one. On a two-person team that's real overhead. It was the right call because the vendor update risk was real and the monitoring overhead was manageable.

---

## 4. Project 2 — Agentic Fitment Assistant

### The Story

Buying wheels is genuinely confusing for normal people. You need to match bolt pattern, offset, hub bore, and wheel diameter — four separate specs — to your specific vehicle trim. Most customers had no idea what any of that meant. They'd guess, pick wrong, and either return the wheel or file a support ticket.

I built an AI fitment assistant that let anyone describe their car in plain English and get accurate, data-backed recommendations. The key architectural decision: constrained tools, not a general agent. The temptation is to give the model broad capability. I did the opposite — the agent could only call four tools: fitment lookup, product classification, lingo translation, and web search fallback. It could not speculate or answer from training data. Every response traced back to a verified data source.

The classification challenge was the hardest part. Third-party product listings are inconsistent — "17x8 +35 5x114.3 73.1 bore black" and "17 inch 8 wide 5 lug 114.3 bolt circle 35mm offset center bore 73.1mm" are the same spec in completely different formats. I built a classification layer using an LLM with a strict output schema that normalized these to a canonical spec object before passing to the lookup. This decoupled the messy input problem from the structured data problem.

First pass had a hallucination problem: the fitment CSV had partial coverage — some vehicles were in the database but with only 60% of their fitment records complete. The agent was answering as if data was complete. I added explicit completeness metadata to the lookup response — if coverage was below a threshold, the agent communicated that explicitly rather than smoothing over the gap.

Built as a white-labeled component deployable as an embedded widget on product pages or a standalone chat interface.

Result: measurably reduced fitment-related support tickets. The assistant contained a class of "will this fit my car" questions that were previously hitting the support queue.

---

### Follow-Up Questions and Answers

**Why constrained tools instead of letting the model answer freely?**

Fitment data is precise. A wheel that doesn't fit is a customer service problem, a return, a trust problem. If the model hallucinates a compatible wheel for a vehicle it doesn't have data on, the customer buys it, it doesn't fit, and we've created more work than the assistant saved.

Constraining to verified data sources meant the worst case was "I don't have data on this vehicle" — honest, useful, and doesn't cause downstream harm. The value of an AI assistant in this domain is not creativity, it's precision. I deliberately designed against model freedom.

**Explain the classification layer — what problem it solves technically**

The fitment database has a canonical schema: `{diameter: 17, width: 8, offset: 35, bolt_pattern: "5x114.3", hub_bore: 73.1}`. Product listings from third-party sources use arbitrary text — sometimes structured, sometimes not.

The classification layer sends the raw listing text to an LLM with a strict JSON schema and instruction to extract only those fields, nothing else. The LLM's output is validated against the schema before being passed to the lookup — if it doesn't conform, the extraction is retried or escalated.

```
Input:  "17 inch 8 wide 5 lug 114.3 bolt circle 35mm offset center bore 73.1mm"
Output: {"diameter": 17, "width": 8, "offset": 35, "bolt_pattern": "5x114.3", "hub_bore": 73.1}
```

This keeps the lookup function clean — it only receives structured inputs, never raw text. Separation of concerns between "understand messy human input" (LLM's job) and "query structured data" (database's job).

**What is an agentic architecture vs a simple LLM call?**

A simple LLM call: you send a prompt, you get a response. One round-trip. The model answers from training data.

An agentic architecture: the model has access to tools — functions it can call to retrieve external information. The model decides which tool to call based on the user's message, calls it, receives the result, and incorporates it into the response. This can loop — the model may call multiple tools in sequence before responding.

```
User: "Will a 17x8 +35 5x114.3 wheel fit a 2018 Honda Civic Sport?"

Agent loop:
  Step 1: call classify("17x8 +35 5x114.3")
          → {diameter:17, width:8, offset:35, bolt_pattern:"5x114.3"}
  Step 2: call fitment_lookup(vehicle="2018 Honda Civic Sport", specs={...})
          → {compatible: true, notes: "within offset range", coverage: 0.92}
  Step 3: formulate response using lookup result — no fabrication
```

**What is the hallucination problem and how did you address it?**

LLMs generate plausible-sounding text based on statistical patterns. When asked about something they don't have data on, they don't say "I don't know" — they generate a confident-sounding answer that may be wrong.

In the fitment context: the CSV had partial coverage. Vehicle X might be in the database but with only 3 of 5 trim levels' fitment data present. The model would call the lookup, get a partial result, and answer as if it had complete data — because the response didn't communicate incompleteness.

Fix: modified the lookup response to include a `coverage_score` field (0–1). If coverage was below 0.8, the agent's instruction set required it to communicate that explicitly: "I have partial fitment data for this vehicle — I can confirm compatibility for the base trim but don't have data for the Sport trim."

The model wasn't hallucinating freely — it was smoothing over a gap the data source left. The fix was making the data source honest about its own gaps.

**What specs actually determine wheel fitment?**

- **Bolt pattern**: number of lug nuts × distance between opposing lugs (e.g., 5×114.3 = 5 lugs, 114.3mm circle). Must match exactly.
- **Hub bore**: center hole diameter in mm. Wheel's bore must be ≥ vehicle's hub. If larger, use hub-centric rings.
- **Offset**: distance in mm from wheel centerline to mounting face. Positive = wheel sits inward. Negative = sits outward. Wrong offset causes rubbing against suspension or fenders.
- **Diameter and width**: overall wheel size. Must match tire size and brake caliper clearance.

All four must be compatible simultaneously. One wrong spec = wheel doesn't mount safely.

---

## 5. Project 3 — Churn and User Behavior Dashboard

### The Story

Nobody internally had a clear picture of where users were dropping off. We had raw event logs in MongoDB but no aggregated view. I noticed a pattern in support tickets — users were getting close to purchasing and not completing. I proposed and built an internal analytics dashboard to surface the problem.

I designed the event schema, built the ETL pipeline from raw logs, built the FastAPI aggregation backend, and a React dashboard for the team.

The obvious assumption was users were dropping at the fitment check — anxiety about compatibility. That was a minor drop-off. The real cliff was between checkout initiation and payment completion — 35% of users who started checkout never finished.

Breaking it down by device: desktop completed at a much higher rate than mobile. Among mobile users who dropped, session logs showed a consistent pattern: checkout page load, idle 30+ seconds, then exit. The payment gateway UI wasn't mobile-optimized — small fields, and it timed out after 60 seconds of inactivity.

The payment gateway was a third-party integration I couldn't rewrite. So I worked around it: added a checkout progress indicator, pre-filled payment form fields from account data, and added a session heartbeat to prevent the 60-second timeout. Surfaced fitment confirmation earlier in the flow so users weren't second-guessing at the payment step.

Result: mobile checkout completion improved. The dashboard became a weekly tool for the team — it surfaced issues that support tickets would never have shown, because most users who have a bad experience don't file a ticket, they just leave.

---

### Follow-Up Questions and Answers

**Walk me through the ETL pipeline — what does each step mean?**

ETL = Extract, Transform, Load.

Extract: pull raw event logs from MongoDB. These are individual events — `{user_id, event_type, timestamp, metadata}`. Thousands of rows per day, one row per user action.

Transform: aggregate raw events into user-level features. For each user, compute: days since last login, number of fitment checks in last 7 days, cart abandonment rate, average session duration, funnel stage reached. This is where the analytical value is — not in the raw events but in the derived features.

Load: write the transformed, user-level feature rows into a clean collection or table that the dashboard and model can query efficiently. Raw logs stay intact — the clean layer is derived from them, never replacing them.

```
Raw:     [event: page_view, user_id: 123, ts: 14:02:01]
         [event: fitment_check, user_id: 123, ts: 14:02:45]
         [event: add_to_cart, user_id: 123, ts: 14:03:12]
         [event: checkout_start, user_id: 123, ts: 14:03:45]
         [event: session_end, user_id: 123, ts: 14:04:20]  ← no purchase

Transformed row for user 123 (that day):
  {user_id: 123, funnel_stage: "checkout_abandoned", session_duration: 139s,
   fitment_checks: 1, device: "mobile", checkout_idle_time: 35s}
```

**What is XGBoost and why use it for churn prediction?**

XGBoost (Extreme Gradient Boosting) is an ensemble model that builds many decision trees sequentially, each one correcting the errors of the previous. The final prediction is a weighted combination of all trees.

Why it works for churn: churn prediction is a tabular data problem. Your features are things like "days since last login", "cart abandonment rate", "device type" — structured rows. XGBoost is empirically the strongest model for tabular data — it handles missing values, non-linear relationships, and feature interactions without you having to engineer them manually.

It outputs a probability score between 0 and 1 — 0.9 means 90% probability this user churns within 30 days. That's more useful than a binary "will churn / won't churn" because you can prioritize interventions — focus effort on 90%+ risk users first.

**How do you define "churn" for an e-commerce marketplace?**

This is the right question to ask before modeling anything. For WheelPrice, I defined churn as: no purchase and no meaningful platform engagement (search, fitment check, product view) for 30 days after their last session. The 30-day window came from analyzing the distribution of time-between-sessions — most returning buyers came back within 30 days. Beyond 30 days, return probability dropped sharply.

You can also define separate churn signals: "likely to not purchase" vs "likely to not return at all." Different interventions for each.

**What was the insight from breaking down by device?**

The funnel analysis at the aggregate level showed a 35% drop between checkout initiation and completion. That's interesting but not actionable — you don't know what to fix.

Segmenting by device showed desktop completion was ~80%, mobile was ~45%. That's a 35-point gap — significant. Segmenting mobile drop-offs by session pattern showed 60%+ of them had >30 seconds of idle time on the checkout page before exiting. The payment gateway had a 60-second idle timeout — exactly matching the pattern.

The data pointed at a specific, fixable cause. That's the value of segmentation — aggregate metrics hide the signal, breakdowns surface it.

**What did you do when the root cause was behind a wall you couldn't touch?**

This is the honest answer: I identified the problem fully, communicated it clearly, and then focused effort on what I could control. The payment gateway timeout was third-party. What I could control:

1. Session heartbeat — a lightweight ping from the frontend to the payment gateway every 30 seconds to reset the idle timer without user action.
2. Pre-fill from account data — reduce how much typing the user had to do on mobile, reducing time-in-form and therefore idle risk.
3. Progress indicator — users who can see they're on step 2 of 3 are less likely to abandon than users facing an opaque form.
4. Moved fitment confirmation earlier — users were second-guessing compatibility at payment. Moving confirmation to the cart step meant they arrived at payment already confident.

None of these required touching the payment gateway.

---

## 6. Project 4 — Fitment Visualizer (Computer Vision)

### The Story

The idea: user uploads a photo of their car, picks a wheel from our listings, we swap the wheel onto their car image. Let them see what it looks like before buying — reduce purchase anxiety, reduce returns.

I used a YOLO object detection model fine-tuned on wheel images to locate wheels in both the user's car photo and the product image. Once I had bounding boxes for each wheel, I cropped the wheel regions, applied perspective correction (homography transform) to match the angle, and blended the new wheel in.

We were planning to move toward an AR-style approach — detect the wheel circle, convert to an ellipse based on viewing angle, overlay a 3D wheel model. We experimented with Snapchat-style filter concepts.

First version results were not production-ready — edge blending was rough, detection on angled or partially visible wheels was inconsistent. We deprioritized it in favor of higher-impact work (the payment gateway issues, the fitment assistant). It's a good feature but the complexity-to-impact ratio at that stage wasn't there.

---

### Follow-Up Questions and Answers

**What is YOLO and how does it work?**

YOLO (You Only Look Once) is a real-time object detection model. Most earlier detection models worked in two stages: first propose regions that might contain objects, then classify each region. YOLO does both in one pass — it divides the image into a grid, and each grid cell predicts bounding boxes and class probabilities simultaneously.

Input: image (resized to fixed dimensions, e.g., 640×640).
Output: list of bounding boxes — each with `{x, y, width, height, class, confidence}`.

"Partially trained" in the context of WheelPrice means I used a pre-trained YOLO checkpoint (trained on COCO — a general object detection dataset) and fine-tuned it on a smaller dataset of wheel images. The base model already knew about shapes and edges; fine-tuning taught it what a wheel looks like specifically. This is transfer learning — you don't train from scratch, you adapt general knowledge to a specific domain.

**What is perspective correction / homography?**

When you photograph a wheel at an angle, the circle appears as an ellipse. If you want to overlay a different wheel, you need to warp it to match that same angle and perspective — otherwise it looks flat and pasted.

A homography is a 3×3 matrix that transforms points in one image plane to corresponding points in another. Given four corresponding point pairs (e.g., corners of the wheel in source and destination), OpenCV can compute the homography and apply it to warp the entire image.

```python
import cv2
import numpy as np

# Four corner points of wheel in source image
src_pts = np.array([[x1,y1],[x2,y2],[x3,y3],[x4,y4]], dtype=np.float32)
# Where they should map to in the destination (car photo angle)
dst_pts = np.array([[a1,b1],[a2,b2],[a3,b3],[a4,b4]], dtype=np.float32)

H, _ = cv2.findHomography(src_pts, dst_pts)
warped = cv2.warpPerspective(wheel_image, H, (width, height))
```

**What is alpha blending and why did edge quality matter?**

Blending is how you composite the new wheel onto the car image so it doesn't look pasted. Naive approach: copy pixel values from wheel image into car image within the bounding box — visible hard edge, looks like a cutout.

Alpha blending uses a mask — a grayscale image where white = fully new wheel, black = fully original car, grey = mix. The border region has a gradient from white to black, which smooths the transition.

```python
# mask: smooth gradient at edges (Gaussian blur of a binary mask)
result = car_img * (1 - mask) + wheel_img * mask
```

The "cartoonish" result in early versions came from: YOLO bounding boxes not being tight enough (irregular border), lighting differences between wheel and car not being corrected, and the blending mask not being smooth enough at edges. All solvable problems — just needed more iteration.

**Why was it deprioritized?**

Honest answer that shows product judgment: the complexity-to-impact ratio wasn't right at that stage. The fitment assistant addressed a problem that was costing real support tickets and real conversions. The visualizer was a nice-to-have that would have required significant CV engineering to get to production quality. Given a two-person team, the choice was clear. Building something halfway and shipping it would have hurt trust more than not shipping it — the cartoonish result was worse than no visualizer.

---

## 7. Cross-Cutting Technical Concepts

### Redis and Caching

Redis is an in-memory key-value store. It's fast because it never touches disk during reads — data lives in RAM, access is O(1).

Used for the blog: server-side rendering a React page against MongoDB takes ~200–500ms under load. With Redis, the rendered HTML is cached for the next N requests. Only the first request pays the full cost.

```
Request → check Redis for cache key "blog:post:best-wheels-civic"
  HIT  → return cached HTML (~1ms)
  MISS → render from MongoDB (~300ms) → store in Redis → return
```

Tag-based invalidation: when post is updated, delete all cache keys tagged with that post's slug. This is more precise than expiring everything — only affected pages regenerate.

### MongoDB vs SQL for This Use Case

MongoDB (document store) was already the platform's database. Blog content maps naturally to documents — a post has an arbitrary nested structure (blocks, images, metadata) that would require multiple SQL joins to represent. Keeping the blog on MongoDB meant no new database, no new connection pooling, no new ops overhead on a two-person team.

Trade-off: MongoDB has weaker consistency guarantees than SQL. For a blog CMS, that's acceptable. For financial or transactional data, you'd use SQL.

### FastAPI vs Flask vs Express

FastAPI was chosen for the aggregation backend because:
- Automatic OpenAPI documentation (the dashboard frontend knew the exact API contract)
- Built-in request validation via Pydantic — incoming requests are type-checked before your code runs
- Native async support — important when the aggregation layer is doing multiple MongoDB queries concurrently
- Faster than Flask for high-concurrency workloads

### Event Schema Design

The most important decision in the dashboard project was what events to track and how to structure them. A bad schema is expensive to fix later — all historical data is in that schema.

```json
{
  "event_id": "uuid",
  "user_id": "string",
  "session_id": "string",
  "event_type": "fitment_check | add_to_cart | checkout_start | purchase",
  "timestamp": "ISO8601",
  "metadata": {
    "device": "mobile | desktop",
    "vehicle_id": "optional",
    "product_id": "optional",
    "page": "string"
  }
}
```

Key decisions: `session_id` links events within one visit. `metadata` is flexible — different event types carry different payloads. `event_type` is an enum — constraining values makes aggregation reliable.

### The Constrained Agent Pattern

The design principle behind the fitment assistant applies broadly: in high-stakes domains, constrain the model's action space rather than expanding it. The value of AI in precision domains is not creativity or fluency — it's structured retrieval and transformation. A model that can only call verified data sources and cannot speculate is more valuable than one that can say anything fluently.

This is the distinction between an LLM as a general assistant and an LLM as a component in a larger system. The latter is more reliable, more auditable, and more deployable.

---

## 8. General WheelPrice Follow-Up Questions

**What was the hardest technical decision you made at WheelPrice?**

The classification layer for the fitment assistant. The easy path was to let the model answer from its training data — it knows what a bolt pattern is, it can probably guess fitment for common vehicles. I made it structurally impossible to do that. The model had to call a tool. Every answer had a paper trail. That was the right call architecturally, but it required building a robust classification layer that could normalize arbitrary product text into structured specs. If that layer failed or misclassified, the lookup failed. Getting it reliable enough to trust — strict schema, retry logic, coverage metadata — was the hardest part.

**What would you do differently?**

On the blog: I'd instrument more aggressively from day one. I added Redis caching after a load spike exposed the problem. I should have anticipated the spike — a blog designed to capture viral social traffic will, by definition, see spikes. Caching should have been in the initial design.

On the dashboard: I'd have pushed harder to get the payment gateway team involved earlier. Once I identified that the gateway timeout was the root cause, I worked around it. But the real fix was a longer timeout or a session heartbeat on the gateway side — that required a vendor conversation that happened too late.

**How did you manage working across four different projects on a two-person team?**

Ruthless prioritization by impact. The fitment assistant and dashboard were actively reducing support load and improving conversion — measurable, direct impact. The visualizer was interesting but speculative — paused it consciously rather than letting it compete for attention with higher-impact work. The blog was foundational — I front-loaded that investment because organic traffic compounds over time. The sequencing mattered as much as the execution.

**What did you ship that you're most proud of?**

The constrained agent architecture for the fitment assistant. It would have been easier and faster to build a general chatbot that answered from training data. I built something more careful: an agent that could only respond through verified tools, that communicated data gaps explicitly rather than smoothing over them, and that was white-labeled and reusable across contexts. The reduction in support tickets was the measurable outcome, but the architectural decision behind it is what I'd defend in a design review.
