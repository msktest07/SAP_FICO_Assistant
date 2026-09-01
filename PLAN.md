# SAP FICO Assistant — Development Plan

## 1. Application Name

**SAP FICO Assistant**

An AI-powered knowledge assistant for SAP Financial Accounting (FI) and Controlling (CO). It helps users understand concepts, configuration, business processes, transactions, reports, integrations, troubleshooting steps, and implementation practices while grounding answers in approved SAP FICO material.

## 2. Problem Statement

SAP FICO knowledge is spread across official documentation, internal process guides, configuration documents, support notes, training material, and expert experience. Users often spend significant time locating the correct information and may receive answers that do not match their SAP product, release, country, or company configuration.

The application should provide one conversational interface for SAP FICO questions and return clear, context-aware, source-backed answers. It must distinguish standard SAP behavior from organization-specific configuration, identify uncertainty, and avoid inventing transaction codes, configuration paths, tables, or accounting guidance.

“Answer all SAP FICO queries” is treated as a coverage goal rather than a guarantee. The production system will use retrieval-augmented generation (RAG), citations, feedback, expert review, and safe escalation when trusted evidence is unavailable.

## 3. Target Users

- SAP FI and CO consultants
- Finance and controlling business users
- Accountants, controllers, and finance managers
- SAP support and help-desk teams
- SAP implementation, migration, and testing teams
- Developers and integration specialists working with FICO
- Auditors and compliance teams, subject to access permissions
- Students, trainees, and certification candidates
- Knowledge administrators and subject-matter experts (SMEs)

## 4. Main Features

### 4.1 Conversational Assistant

- Natural-language questions with multi-turn context
- Coverage of FI areas such as General Ledger, Accounts Payable, Accounts Receivable, Asset Accounting, Bank Accounting, closing, taxes, and financial reporting
- Coverage of CO areas such as cost centers, internal orders, profit centers, product costing, profitability analysis, allocations, planning, and period-end closing
- Support for configuration, process, conceptual, reporting, integration, migration, testing, and troubleshooting questions
- Structured answers with prerequisites, numbered steps, cautions, examples, and expected results where appropriate
- Follow-up questions when product/version or business context materially affects the answer
- Conversation history, rename, search, archive, and delete

### 4.2 Grounded Knowledge and Citations

- RAG over approved official and organization-owned content
- Citations linked to the exact source and relevant section/page
- Metadata filters for SAP ECC vs. SAP S/4HANA, release, deployment model, module, country, language, and organization
- Clear labels separating standard SAP guidance from company-specific procedures
- “Insufficient evidence” response and escalation route when reliable content is unavailable
- Answer confidence/evidence indicator based on retrieval quality, not unsupported model certainty

### 4.3 SAP-Aware Answer Tools

- Transaction-code and Fiori-app explanations, with release applicability
- SPRO/configuration-path guidance
- Tables, important fields, document flow, and master-data relationships
- FI/CO integration guidance for MM, SD, AA, PP, PS, HCM, Treasury, and related modules
- Accounting-entry examples with explicit assumptions
- Test-case and test-data generation for supported business scenarios
- Error-message analysis using the message class/number and relevant system context
- Glossary for SAP and finance terminology

### 4.4 User Context and Personalization

- Optional user profile: role, experience level, preferred language, SAP product/release, country, and preferred answer depth
- Session-level context selector to prevent incorrect cross-system assumptions
- Bookmarks, saved answers, and export to Markdown/PDF where policy permits

### 4.5 Feedback and Continuous Improvement

- Helpful/not-helpful rating and reason selection
- User correction or missing-content submission
- SME review queue for weak, disputed, or high-risk answers
- Curated FAQ and approved-answer publishing workflow
- Quality analytics: unanswered topics, citation coverage, retrieval relevance, and user satisfaction

### 4.6 Administration and Governance

- Upload, connect, classify, version, re-index, and retire knowledge sources
- Role-based access control (RBAC) and document-level permissions
- User and role management
- Prompt, model, retrieval, and feature configuration with version history
- Audit logs for questions, responses, sources, feedback, and administrative actions
- Configurable retention, redaction, and deletion policies
- Prompt-injection defenses and isolation of instructions found inside documents

### 4.7 Non-Functional Requirements

- Responsive, accessible interface targeting WCAG 2.2 AA
- Streaming answers and clear progress/error states
- Initial targets: first response token within 3 seconds and complete common answers within 15 seconds, excluding provider or document-processing delays
- Encryption in transit and at rest; secrets held in a managed secret store
- Tenant and data isolation for enterprise use
- Horizontal scalability for chat and ingestion workers
- Monitoring, tracing, rate limiting, backups, and disaster recovery
- No direct production SAP changes in the initial release; the assistant provides guidance only

## 5. Pages and Screens Required

| Page/Screen | Purpose |
|---|---|
| Sign in / SSO | Authenticate through enterprise SSO or local development login. |
| Onboarding | Capture role, experience, language, and default SAP context. |
| Home | Show a search/chat entry, topic shortcuts, recent chats, and example questions. |
| Chat workspace | Display conversation, streaming response, citations, context selectors, feedback, copy, save, and export actions. |
| Source viewer | Open the cited document at the relevant page/section and display source metadata. |
| Conversation history | Search, filter, rename, archive, and delete past chats. |
| Saved items | Manage bookmarked answers, sources, and approved FAQs. |
| Glossary / topic explorer | Browse FI/CO domains, terminology, transactions, and learning paths. |
| Feedback / support | Report incorrect answers, submit corrections, or request SME help. |
| User settings | Manage profile, SAP context, language, answer detail, privacy, and notification preferences. |
| Admin dashboard | View adoption, quality, latency, cost, ingestion, and unresolved-question metrics. |
| Knowledge management | Upload/connect sources, edit metadata and permissions, monitor processing, version, and retire documents. |
| Review queue | Let SMEs review reported answers and publish approved corrections or FAQs. |
| User and role management | Assign users, roles, groups, and knowledge access. |
| Audit and system settings | Inspect audit events and configure models, prompts, retrieval, retention, and integrations. |

The MVP requires sign-in, home, chat, source viewer, history, settings, basic knowledge management, and feedback. The other screens can follow in later releases.

## 6. Technology Stack

### Recommended Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js, React, TypeScript | Responsive web application and server-side rendering where useful. |
| UI | Tailwind CSS, shadcn/ui | Consistent, accessible components and rapid interface development. |
| API | Python, FastAPI, Pydantic | Typed chat, retrieval, feedback, ingestion, and administration APIs. |
| AI orchestration | Provider-neutral service layer; optional LangGraph/LlamaIndex components | Prompt flow, retrieval, citations, tool use, and model portability. |
| LLM/embeddings | Configurable enterprise-approved providers | Answer generation and semantic embeddings without locking business logic to one vendor. |
| Primary database | PostgreSQL | Users, conversations, metadata, permissions, feedback, and audit records. |
| Vector search | PostgreSQL with pgvector initially | Semantic retrieval with simple operations; move to a dedicated vector service only when scale requires it. |
| Cache/session/rate limits | Redis | Short-lived caching, queues, distributed locks, and throttling. |
| Background processing | Celery or Dramatiq workers | Document extraction, chunking, embedding, re-indexing, and exports. |
| Object storage | S3-compatible storage / Azure Blob Storage | Original documents, processed artifacts, and generated exports. |
| Authentication | Microsoft Entra ID via OIDC/OAuth 2.0; development fallback | Enterprise SSO and group/role mapping. |
| Observability | OpenTelemetry, structured logs, Prometheus/Grafana or managed equivalents | Traces, logs, metrics, alerts, quality, and cost monitoring. |
| Testing | Pytest, Vitest, React Testing Library, Playwright, RAG evaluation dataset | Unit, integration, end-to-end, security, and answer-quality testing. |
| Infrastructure | Docker, Terraform, GitHub Actions or Azure DevOps | Repeatable environments and CI/CD. |

Technology choices should be confirmed against the organization's cloud, identity, data-residency, licensing, and approved-AI-provider requirements before implementation.

## 7. Proposed Project Folder Structure

```text
SAP_FICO_Assistant/
├── PLAN.md
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── apps/
│   ├── web/                         # Next.js frontend
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── lib/
│   │   ├── public/
│   │   └── tests/
│   └── api/                         # FastAPI backend
│       ├── app/
│       │   ├── api/                 # HTTP routes and dependencies
│       │   ├── core/                # Config, security, logging
│       │   ├── models/              # Database models
│       │   ├── schemas/             # Request/response schemas
│       │   ├── services/            # Chat, users, feedback, audit
│       │   ├── retrieval/           # Search, ranking, citations
│       │   ├── ingestion/           # Parse, chunk, embed, index
│       │   ├── prompts/             # Versioned prompt templates
│       │   └── workers/             # Background jobs
│       ├── migrations/
│       └── tests/
├── packages/
│   ├── shared-types/                # Shared API contracts
│   ├── ui/                          # Reusable UI components
│   └── evals/                       # Golden questions and evaluators
├── knowledge/
│   ├── sample/                      # Licensed/sample local documents only
│   ├── metadata/                    # Taxonomy and source definitions
│   └── README.md
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── security/
│   └── runbooks/
├── infra/
│   ├── docker/
│   ├── terraform/
│   └── monitoring/
├── scripts/                         # Safe development and maintenance scripts
└── .github/workflows/               # CI/CD pipelines
```

## 8. Data That Needs to Be Stored

### Core Application Data

- Users, identity-provider subject IDs, roles, groups, preferences, and default SAP context
- Organizations/tenants and feature/configuration settings
- Conversations, messages, model responses, timestamps, and message status
- Bookmarks, saved answers, exports, and recent activity
- Feedback, correction proposals, review status, and SME decisions

### Knowledge and Retrieval Data

- Source records: title, owner, URI, type, language, module, topic, product, release, country, organization, validity dates, confidentiality, checksum, and version
- Original files or secure external references
- Extracted text, sections, pages, tables, chunks, and embeddings
- Access-control metadata for every source/chunk
- Ingestion runs, parsing errors, index versions, and source lifecycle state
- Curated questions, approved answers, glossary terms, and synonyms

### AI, Quality, and Operations Data

- Answer-to-source citation mappings and retrieval scores
- Prompt, model, embedding, retrieval, and safety-policy versions used for each response
- Token use, latency, errors, cache information, and estimated cost
- Evaluation datasets, expected facts/citations, test runs, and quality scores
- Security and audit events, including administrative changes and document access

### Data Rules

- Do not ingest SAP content unless licensing and access rights permit it.
- Do not store passwords or provider keys in application tables; use a managed secret store.
- Minimize personal and financial data, redact sensitive values before sending them to an LLM, and prevent such data from entering logs.
- Apply tenant and document permissions during retrieval, before content is supplied to the model.
- Define retention and deletion schedules for chats, feedback, logs, documents, and embeddings.
- Back up metadata and source objects; regularly test restoration.

## 9. Development Steps

### Phase 0 — Discovery and Governance (1–2 weeks)

1. Interview representative consultants, finance users, support staff, SMEs, security, and compliance stakeholders.
2. Prioritize supported FI/CO domains, languages, SAP products/releases, and top question types.
3. Inventory content and confirm ownership, licensing, confidentiality, freshness, and access rules.
4. Define measurable success criteria: answer correctness, citation correctness, groundedness, retrieval recall, latency, satisfaction, and unresolved-query rate.
5. Define prohibited behavior, including unsupported financial advice and direct production-system changes.

**Exit criteria:** approved scope, content inventory, risk register, architecture decisions, and an initial set of 100–300 representative evaluation questions.

### Phase 1 — Foundation and UX (1–2 weeks)

1. Create the monorepo, local Docker environment, linting, formatting, tests, and CI.
2. Define database schema, API contract, RBAC model, taxonomy, and environment configuration.
3. Produce accessible wireframes for home, chat, citations, history, settings, and administration.
4. Implement authentication skeleton, frontend shell, health endpoints, logging, and trace correlation.

**Exit criteria:** deployable application shell, automated checks, reviewed UX, and documented local setup.

### Phase 2 — Knowledge Ingestion and Retrieval (2–4 weeks)

1. Implement source upload/connectors for the first approved formats, starting with PDF, DOCX, HTML, Markdown, and text.
2. Extract headings, pages, tables, and metadata; preserve page/section references for citations.
3. Build configurable chunking, embedding, indexing, metadata filtering, and versioning.
4. Add hybrid retrieval (semantic plus keyword), reranking, duplicate handling, and permission filtering.
5. Create an ingestion dashboard with status, errors, reprocessing, and retirement controls.
6. Measure retrieval recall and citation precision using the evaluation set.

**Exit criteria:** approved sources are searchable, citations resolve correctly, permissions are enforced, and retrieval meets agreed quality thresholds.

### Phase 3 — Assistant MVP (2–4 weeks)

1. Implement chat sessions, streaming, conversation context, history, and SAP context selectors.
2. Build the grounded-answer pipeline: query analysis, retrieval, reranking, answer generation, citations, and evidence checks.
3. Add SAP-aware response templates for concepts, configuration, transactions/apps, errors, comparisons, and test cases.
4. Add source viewer, feedback, bookmarks, input validation, rate limits, and graceful failure states.
5. Add prompt-injection protections, content boundaries, redaction, and “insufficient evidence” behavior.
6. Create unit, integration, end-to-end, and golden-question evaluation tests.

**Exit criteria:** users can ask supported questions and receive useful, cited answers; critical security and quality tests pass.

### Phase 4 — Administration and Enterprise Readiness (2–3 weeks)

1. Complete SSO, group-to-role mapping, tenant isolation, document-level permissions, and audit trails.
2. Add SME review workflow, approved FAQs, knowledge lifecycle controls, and quality dashboard.
3. Add monitoring for availability, latency, errors, retrieval quality, unsafe inputs, token use, and cost.
4. Conduct threat modeling, dependency/container scans, penetration testing, accessibility testing, load testing, backup/restore testing, and privacy review.
5. Write operational runbooks, support procedures, incident response, and user/admin documentation.

**Exit criteria:** security and operational reviews pass and production readiness is approved.

### Phase 5 — Pilot, Launch, and Improvement (2–4 weeks, then ongoing)

1. Pilot with a small cross-functional group using real but approved questions.
2. Review weak answers with SMEs; improve documents, metadata, retrieval, prompts, and evaluation cases.
3. Use a release gate requiring no critical hallucinations in high-risk test categories and agreed thresholds for citation correctness, groundedness, latency, and satisfaction.
4. Roll out progressively by team or tenant with usage and cost limits.
5. Establish a regular content freshness review and regression-evaluation schedule.

**Exit criteria:** pilot acceptance, production launch approval, assigned operational ownership, and a measured improvement backlog.

### Later Enhancements

- Multilingual queries and answers with language-specific evaluation
- Voice input and accessible read-aloud responses
- Microsoft Teams or Slack interface
- Approved read-only integrations to fetch contextual SAP information
- Fiori deep links and system-aware navigation where authorized
- Diagram, process-flow, and test-document generation
- Human handoff and ticketing integration

Any write-back or autonomous action in SAP should be a separate project with explicit approvals, least-privilege technical users, validation, auditability, and human confirmation.

## 10. Deployment Approach

### Environments

Use separate **development**, **test**, **staging**, and **production** environments. Each environment must have isolated databases, object storage, indexes, credentials, identity configuration, and model-provider settings. Production knowledge must not be copied to lower environments without approved masking and controls.

### Packaging and Infrastructure

- Package the web app, API, and workers as separate Docker images.
- Use managed PostgreSQL/pgvector, Redis, object storage, secret management, and an approved managed LLM endpoint where possible.
- Deploy containers to the organization's preferred platform, such as Azure Container Apps or AKS, AWS ECS/EKS, or an equivalent private platform.
- Provision infrastructure through Terraform and keep environment differences in validated configuration rather than code branches.
- Keep services and data in approved regions; use private networking and private endpoints when required.

### CI/CD Pipeline

1. On pull requests: run formatting, linting, type checks, unit tests, secret scanning, dependency scanning, and build validation.
2. On merge: build immutable images, generate a software bill of materials, scan/sign images, and deploy automatically to development/test.
3. Run API integration tests, browser tests, migration checks, security checks, and the RAG regression suite.
4. Promote the same image to staging, run smoke/load/quality tests, and require approval for production.
5. Deploy production with rolling or blue/green releases, database migration safeguards, health checks, and a documented rollback process.

### Production Operations

- Autoscale stateless web/API services and ingestion workers independently.
- Alert on availability, latency, error rate, queue backlog, database health, retrieval failures, answer-quality regression, and spend.
- Use structured, redacted logs and end-to-end traces without recording unnecessary question/document content.
- Schedule encrypted backups and point-in-time database recovery; test recovery at defined intervals.
- Version prompts, models, indexes, and knowledge sources so any answer can be investigated and releases can be rolled back.
- Use canary releases for significant model, embedding, prompt, or retrieval changes and compare them against the fixed evaluation suite.

## 11. Initial Definition of Done

The first production release is complete when:

- Users can authenticate, select their SAP context, ask FI/CO questions, and receive responsive answers with working citations.
- The assistant refuses to guess when evidence is insufficient and clearly communicates assumptions and version differences.
- Approved content can be ingested, versioned, permissioned, re-indexed, and retired by administrators.
- Conversation history, feedback, source viewing, auditing, and required retention/deletion controls work end to end.
- Automated functional, security, accessibility, performance, retrieval, and answer-quality tests meet agreed thresholds.
- Monitoring, backups, rollback, incident response, documentation, and named business/technical ownership are in place.

