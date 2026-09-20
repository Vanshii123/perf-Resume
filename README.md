# Fit Verifier

**Live app:** https://main.d3etzdqbimzdoi.amplifyapp.com/

An evidence-first resume-to-job-description matching engine. Instead of guessing whether you're a fit for a role, Fit Verifier gives you a fit score where every single data point — every matched skill, every gap — traces back to an exact, clickable line in your resume or the job posting. No black-box AI score. No unverifiable AI-written bullet points.

---

## The problem

Every job seeker has felt this: you read a job description, you *think* you're qualified, but you're not sure which specific line in your resume actually proves it — and you have no idea what's actually missing. On the other side, AI resume-tailoring tools have made this worse: they happily generate polished bullet points that quietly invent skills or metrics you never had, which is a fabrication risk both for candidates and for anyone reading that resume downstream.

Fit Verifier exists to remove the guessing and the fabrication risk from both sides of that problem.

## What it does

1. **Upload your resume (PDF) + paste a job description.**
2. **Get a fit score with a full breakdown** — every required skill in the JD is checked against your resume using deterministic string/token matching (no LLM guesswork), and every match links to the exact resume sentence that supports it.
3. **See exactly what's missing** — a plain list of required skills your resume doesn't currently show evidence for.
4. **(Enhancement layer) Get JD-tailored resume bullets** — an LLM rewrites your bullets to speak the job description's language, but every generated bullet is run back through a **fabrication-check**: if it introduces a claim (a skill, a tool, a number) that isn't traceable to your original resume text, it's rejected before you ever see it.

The core idea: a fit score or a rewritten bullet is only useful if you can trust it. So every claim the system makes has a receipt.

## Architecture

```
Resume (PDF) ──┐
                ├──▶ Resume Parser ──▶ Deterministic Scoring Engine ──▶ Fit Score + Evidence Ledger
Job Description ┘                                                        (no LLM — pure matching logic)
                                              │
                                              ▼
                                    LLM Tailoring Agent
                                    (rewrites bullets in JD language)
                                              │
                                              ▼
                                    Fabrication / Evidence Check
                                    (rejects any unsupported claim)
                                              │
                                              ▼
                                    Verified, JD-aligned bullets
```

**Deployment:**
- **Backend** — FastAPI service deployed on **AWS EC2** (Free Tier), with an Elastic IP so the endpoint is stable across restarts.
- **Frontend** — React (Vite) app deployed on **AWS Amplify Hosting**.
- **File handling** — PDF text extraction via PyMuPDF on the backend.

## Why the scoring engine is deterministic, not LLM-based

This was a deliberate design choice, not a limitation. A fit score that comes from an LLM is a black box — it can't tell you *why* it gave you that number, and it can hallucinate matches that aren't really there. Our scoring engine uses fuzzy string matching (character-level + token-set overlap) against the resume's actual sentences, so:
- The score is fully explainable — you can always see the exact evidence.
- It works even when no LLM is available (which mattered a lot during this build — see "What we learned" below).
- It can never invent a match that doesn't exist in the text.

The LLM only enters the picture for the *optional* enhancement layer (bullet tailoring), and even there, its output is checked by the same deterministic logic before it reaches the user.

## What we learned

Four LLM providers, four different authentication models. Over the course of this build we integrated (in order) AWS Bedrock, Anthropic's API, Google Gemini, and finally Groq — each time hitting a different flavor of auth failure (credential resolution, deprecated SDKs, OAuth-vs-API-key mismatches, model deprecation). Debugging this under time pressure taught us to build the LLM-calling layer as a swappable, provider-agnostic function rather than hardwiring one vendor's SDK into the business logic — so a provider swap becomes a single function replacement instead of a rewrite.

## Honest tradeoffs & what's next

- The tailoring layer (LLM-generated bullets) is dependent on LLM provider availability, and during our final testing window we hit intermittent provider-side issues that meant this layer wasn't consistently producing output. The deterministic scoring and evidence engine — the core of the product — was unaffected and fully functional throughout.
- **Next steps:** add automatic provider fallback/retry so tailoring degrades gracefully across providers instead of depending on one; add a lightweight GitHub cross-check that verifies a resume's claimed tech stack against the candidate's actual repositories; move the backend behind HTTPS with a proper reverse proxy for production use.

## Tech stack

- **Backend:** Python, FastAPI, PyMuPDF, deterministic fuzzy-matching (difflib + token-set ratio)
- **Frontend:** React, Vite, Tailwind CSS
- **AI tools used during development:** Claude (Anthropic), Google Antigravity / Codex
- **Cloud:** AWS EC2, AWS Amplify Hosting

## Team

Built during the First Commit hackathon (Bharat Builds Tour, AWS × WeMakeDevs).
