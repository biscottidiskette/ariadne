# BACKLOG.md

# Ariadne — IR Decision Engine
### LLM-Assisted Incident Response Platform

---

## Legend
| Symbol | Meaning |
|--------|---------|
| 🔴 | Blocked |
| 🟡 | In Progress |
| 🟢 | Complete |
| ⚪ | Not Started |
| 🔵 | Post-MVP |

---

## EPIC 1: Environment & Project Scaffold
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E1-01 | Ubuntu 22.04 system dependencies | 🟢 | apt packages installed |
| E1-02 | Python 3.10+ virtual environment | 🟢 | venv created, activated |
| E1-03 | Python dependencies installed | 🟢 | requirements.txt locked |
| E1-04 | Node.js 20.x installed | 🟢 | via NodeSource |
| E1-05 | React + Vite frontend scaffold | 🟢 | JavaScript template |
| E1-06 | Frontend npm dependencies installed | 🟢 | axios, router, query, etc. |
| E1-07 | Git initialized with .gitignore | 🟢 | secrets excluded |
| E1-08 | .env.example documented | 🟢 | |
| E1-09 | Initial commit | 🟢 | project scaffold |
| E1-10 | Project named — Ariadne | 🟢 | |

---

## EPIC 2: Database Layer
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E2-01 | `db/db.py` — SQLite connection, pragmas, init | ⚪ | |
| E2-02 | `db/db.py` — schema: engagements table | ⚪ | |
| E2-03 | `db/db.py` — schema: artifacts table | ⚪ | |
| E2-04 | `db/db.py` — schema: messages table | ⚪ | |
| E2-05 | `db/db.py` — schema: suggestions table | ⚪ | anti-circular engine |
| E2-06 | `db/db.py` — schema: iocs table | ⚪ | |
| E2-07 | `db/db.py` — schema: timeline_events table | ⚪ | |
| E2-08 | `db/db.py` — schema: playbook_steps table | ⚪ | |
| E2-09 | `db/db.py` — schema: sigma_rules table | ⚪ | |
| E2-10 | `db/db.py` — schema: notes table | ⚪ | timestamped, freeform |
| E2-11 | `db/database_service.py` — abstraction controller | ⚪ | swap point for future DBs |
| E2-12 | DB migration strategy — versioned ALTER scripts | ⚪ | simple, no Alembic for MVP |

---

## EPIC 3: Models & Schemas
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E3-01 | `models/schemas.py` — Engagement models | ⚪ | create, read, update, status |
| E3-02 | `models/schemas.py` — Artifact models | ⚪ | upload + paste variants |
| E3-03 | `models/schemas.py` — Message models | ⚪ | chat history |
| E3-04 | `models/schemas.py` — Suggestion models | ⚪ | with status enum |
| E3-05 | `models/schemas.py` — IoC models | ⚪ | typed: IP, hash, domain, path, etc. |
| E3-06 | `models/schemas.py` — Timeline event models | ⚪ | |
| E3-07 | `models/schemas.py` — Playbook models | ⚪ | |
| E3-08 | `models/schemas.py` — Sigma rule models | ⚪ | |
| E3-09 | `models/schemas.py` — Note models | ⚪ | |

---

## EPIC 4: AI Layer
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E4-01 | `ai/groq.py` — Groq client initialization | ⚪ | loads from .env |
| E4-02 | `ai/groq.py` — async chat completion | ⚪ | |
| E4-03 | `ai/groq.py` — streaming response support | ⚪ | for chat UX |
| E4-04 | `ai/groq.py` — model selection + fallback | ⚪ | llama3-70b default |
| E4-05 | `ai/groq.py` — token usage tracking | ⚪ | logged per request |
| E4-06 | `ai/groq.py` — error handling + retry logic | ⚪ | rate limits, timeouts |
| E4-07 | `ai/ai.py` — LLM controller abstraction | ⚪ | routes to groq.py, swap point |
| E4-08 | `ai/ai.py` — system prompt builder | ⚪ | injects engagement context |
| E4-09 | `ai/ai.py` — anti-circular suggestion injector | ⚪ | injects prior suggestions into prompt |
| E4-10 | `ai/ai.py` — suggestion extractor | ⚪ | parses LLM response for new suggestions |
| E4-11 | `ai/ai.py` — context window manager | ⚪ | trims history to stay within token limits |

---

## EPIC 5: Artifact Parsers
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E5-01 | `parsers/parser_registry.py` — routes artifact to correct parser | ⚪ | detects type by extension + content |
| E5-02 | `parsers/evtx_parser.py` — raw .evtx file parser | ⚪ | via python-evtx |
| E5-03 | `parsers/chainsaw_parser.py` — Chainsaw JSON output parser | ⚪ | normalized event format |
| E5-04 | `parsers/ioc_parser.py` — extract IPs, hashes, domains, paths | ⚪ | regex + validation |
| E5-05 | `parsers/edr_parser.py` — EDR alert normalization | ⚪ | generic + CrowdStrike/SentinelOne flavors |
| E5-06 | `parsers/siem_parser.py` — SIEM query result normalization | ⚪ | Splunk, Elastic, QRadar outputs |
| E5-07 | `parsers/sigma_parser.py` — ingest existing Sigma rules | ⚪ | YAML parse + validate |
| E5-08 | `parsers/prefetch_parser.py` — PECmd output parser | ⚪ | execution artifacts |
| E5-09 | `parsers/registry_parser.py` — RECmd output parser | ⚪ | persistence, lateral movement |
| E5-10 | `parsers/memory_parser.py` — Volatility / memory strings | ⚪ | process lists, network conns |
| E5-11 | `parsers/scheduled_task_parser.py` — XML task dump parser | ⚪ | persistence artifacts |
| E5-12 | `parsers/paste_parser.py` — freeform paste handler | ⚪ | best-effort type detection |

---

## EPIC 6: Backend Services
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E6-01 | `services/case_service.py` — engagement CRUD | ⚪ | create, read, update, delete, list |
| E6-02 | `services/case_service.py` — engagement status transitions | ⚪ | active/contained/closed/archived |
| E6-03 | `services/case_service.py` — lead_id stub | ⚪ | multi-seat ready post-MVP |
| E6-04 | `services/artifact_service.py` — file upload handler | ⚪ | async, size-limited |
| E6-05 | `services/artifact_service.py` — paste handler | ⚪ | routes to parser_registry |
| E6-06 | `services/artifact_service.py` — normalized storage | ⚪ | stores raw + parsed form |
| E6-07 | `services/chat_service.py` — message persistence | ⚪ | full history per engagement |
| E6-08 | `services/chat_service.py` — suggestion lifecycle | ⚪ | create, update status, query by engagement |
| E6-09 | `services/chat_service.py` — context builder | ⚪ | assembles history for LLM submission |
| E6-10 | `services/timeline_service.py` — event CRUD | ⚪ | |
| E6-11 | `services/timeline_service.py` — auto-extract from artifacts | ⚪ | pulls timestamps on ingest |
| E6-12 | `services/timeline_service.py` — chronological sort + gap detection | ⚪ | |
| E6-13 | `services/playbook_service.py` — LLM-driven playbook generation | ⚪ | per engagement context |
| E6-14 | `services/playbook_service.py` — step status tracking | ⚪ | pending/complete/skipped |
| E6-15 | `services/playbook_service.py` — playbook export | ⚪ | markdown output |
| E6-16 | `services/sigma_service.py` — LLM-driven Sigma rule drafting | ⚪ | from IoC context |
| E6-17 | `services/sigma_service.py` — rule validation | ⚪ | YAML structure check |
| E6-18 | `services/sigma_service.py` — rule export | ⚪ | .yml file download |
| E6-19 | `services/ioc_service.py` — IoC CRUD | ⚪ | |
| E6-20 | `services/ioc_service.py` — relationship mapping | ⚪ | links IoC → process → host → event |
| E6-21 | `services/note_service.py` — timestamped note append | ⚪ | freeform, hits LLM context |

---

## EPIC 7: API Routes
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E7-01 | `main.py` — FastAPI app init, CORS, middleware | ⚪ | |
| E7-02 | `routes/engagements.py` — full CRUD endpoints | ⚪ | |
| E7-03 | `routes/artifacts.py` — upload + paste endpoints | ⚪ | |
| E7-04 | `routes/chat.py` — send message, stream response | ⚪ | SSE streaming |
| E7-05 | `routes/suggestions.py` — list, update status | ⚪ | |
| E7-06 | `routes/timeline.py` — list, add, update events | ⚪ | |
| E7-07 | `routes/playbook.py` — generate, list steps, export | ⚪ | |
| E7-08 | `routes/sigma.py` — generate rule, list, export | ⚪ | |
| E7-09 | `routes/iocs.py` — list, add, relationship data | ⚪ | |
| E7-10 | `routes/notes.py` — append, list | ⚪ | |
| E7-11 | `routes/graph.py` — artifact relationship graph data | ⚪ | node + edge format for frontend |

---

## EPIC 8: Frontend — Engagement Management
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E8-01 | App shell — router, layout, theme | ⚪ | SOC dashboard dark theme |
| E8-02 | Engagement list page — full CRUD | ⚪ | landing page |
| E8-03 | Engagement card component — status badge, metadata | ⚪ | |
| E8-04 | New engagement modal — form + validation | ⚪ | |
| E8-05 | Engagement status indicator — color coded | ⚪ | active/contained/closed/archived |
| E8-06 | Delete + archive confirmation dialog | ⚪ | |

---

## EPIC 9: Frontend — Engagement Workspace
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E9-01 | Workspace layout — tabbed + persistent sidebar | ⚪ | |
| E9-02 | Chat tab — message thread, streaming responses | ⚪ | |
| E9-03 | Chat — paste artifact button + modal | ⚪ | |
| E9-04 | Chat — upload artifact button + file picker | ⚪ | |
| E9-05 | Chat — clear context confirmation | ⚪ | |
| E9-06 | Chat — message status indicators | ⚪ | sent/thinking/streaming/error |
| E9-07 | Findings tab — parsed artifact viewer | ⚪ | normalized display per type |
| E9-08 | Notes tab — append note, timestamped list | ⚪ | |
| E9-09 | Timeline tab — chronological event view | ⚪ | |
| E9-10 | Timeline — manual event add | ⚪ | |
| E9-11 | Playbook tab — generated steps, status checkboxes | ⚪ | |
| E9-12 | Sigma tab — generated rules, syntax highlighted | ⚪ | |
| E9-13 | IoC tab — table view, type badges | ⚪ | |
| E9-14 | Relationship graph tab — force-directed graph | ⚪ | react-force-graph-2d |
| E9-15 | Suggested next queries sidebar — persistent, live-updating | ⚪ | separate from chat |
| E9-16 | Suggestion status controls — mark tried/worked/failed | ⚪ | |
| E9-17 | LLM status indicator — connection + model display | ⚪ | |

---

## EPIC 10: Post-MVP
| ID | Task | Status | Notes |
|----|------|--------|-------|
| E10-01 | Report generator — full engagement export | 🔵 | markdown + PDF |
| E10-02 | Multi-user seats — lead_id → auth system | 🔵 | JWT auth |
| E10-03 | PostgreSQL migration — db swap via database_service.py | 🔵 | |
| E10-04 | Additional LLM providers — OpenAI, Anthropic, Ollama | 🔵 | via ai.py swap |
| E10-05 | Ollama local model support — air-gapped deployments | 🔵 | critical for sensitive IR |
| E10-06 | MITRE ATT&CK mapping — tag IoCs + playbook steps to TTPs | 🔵 | |
| E10-07 | Sigma rule testing — validate against sample logs | 🔵 | |
| E10-08 | Velociraptor artifact integration | 🔵 | |
| E10-09 | VirusTotal / OTX IoC enrichment | 🔵 | automated reputation lookups |
| E10-10 | Case export — STIX/TAXII format | 🔵 | threat intel sharing |
| E10-11 | Dark/light theme toggle | 🔵 | SOC dark default |
| E10-12 | Keyboard shortcuts — power user navigation | 🔵 | |

---

## Known Risks & Design Decisions
| # | Item | Decision |
|---|------|----------|
| R1 | LLM circular suggestions | Suggestion table with status injected into every system prompt as hard constraint |
| R2 | Context window limits | chat_service.py trims oldest non-critical messages first, preserves IoCs + suggestions |
| R3 | Large artifact files (evtx, memory dumps) | Parse + summarize on ingest, never send raw to LLM |
| R4 | API key exposure | .env gitignored, .env.example committed as template |
| R5 | SQLite concurrency | Single-user MVP, WAL mode enabled in db.py for read concurrency |
| R6 | Vendor-specific Sigma | All rules drafted in portable Sigma, conversion handled by sigmatools post-MVP |

---

## Build Order (MVP Critical Path)
```
E1 (scaffold) → E2 (database) → E3 (schemas) → E4 (AI layer)
→ E5 (parsers) → E6 (services) → E7 (routes) → E8 (frontend engagements)
→ E9 (frontend workspace) → SHIP MVP
```

---

*Last updated: project kickoff*
*Next: E2-01 — db/db.py*
