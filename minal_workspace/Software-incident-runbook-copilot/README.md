# Software Incident and Runbook Copilot

An internal, read-only incident triage prototype. This project lives separately from the Job Search Assistant. The current implementation can parse and chunk the synthetic corpus, fit a local BM25 encoder, index dense+sparse vectors in Pinecone, retrieve evidence through a LangChain retriever, and generate citation-constrained triage responses through LangChain's OpenAI integration.

## Use case

Help an on-call engineer triage an alert by combining approved runbooks, architecture documentation, postmortems, and mock incident evidence, then recommend cited checks or escalation. The interface is Streamlit. The agent is advisory and read-only: it has no production mutation tools and cannot deploy, roll back, scale, change configuration, or execute commands.

**RAG goal:** Help on-call engineers answer incident root-cause and next-step questions from the 18 synthetic runbooks, architecture documents, and postmortems plus selected telemetry fixtures in Streamlit chat, with a target of **at least 90% statement faithfulness** and **p95 triage latency of at most 15 seconds**. These are targets, not claims about current performance.

## Seed corpus

All content in this prototype is synthetic and fictional. It is written as English Markdown with YAML front matter, plus JSON files that represent mock alert/telemetry tool responses.

- 6 active runbooks plus 1 explicitly superseded archived runbook: Kafka consumer lag, database pool saturation, provider timeouts, checkout 5xx, Kubernetes crash loops, and Redis cache stampedes.
- 5 architecture documents: service map, checkout/event flow, alert semantics, change/rollback policy, and ownership/escalation.
- 6 postmortems: five resolved incidents and one deliberately inconclusive incident to test abstention.
- 6 synthetic incident snapshots: alert and telemetry evidence, kept separate from the searchable prose corpus. Three include representative Splunk-style search results.
- 28 labeled evaluation questions: direct lookup, diagnosis, prevention, similar-incident discrimination, conflicting/stale evidence, safety boundaries, and insufficient-evidence cases.

For a real deployment, service owners remain authoritative for runbooks and architecture docs; the incident-management system owns postmortems; observability systems own alerts and telemetry. This sample corpus is a learning fixture, not a production source of truth.

## Ingestion and cleaning contract

Prototype ingestion is local and explicit: Markdown documents are indexed when the operator requests it. Alert and telemetry JSON files are loaded separately as local read-only fixtures and are not indexed. Keep each source document unchanged on disk and store a content hash, source path, `doc_id`, version, owner, service, environment, and review timestamp with each indexed record.

Before chunking:

- Decode HTML entities and normalize line endings and repeated whitespace.
- Remove navigation, page chrome, and duplicated export boilerplate, but retain headings, lists, tables, code blocks, warnings, negations, thresholds, units, and exact identifiers.
- Strip script/style markup if a future HTML connector is added; do not strip meaningful Markdown structure.
- Redact secrets, tokens, customer identifiers, and personal data. Do not ingest raw production logs into the document index.
- Validate required metadata and mark documents stale or superseded instead of silently combining versions.

The seed files are already plain Markdown/JSON. The parser currently normalizes line endings/whitespace, decodes HTML entities, strips HTML tags and script/style blocks, removes known page boilerplate, validates required metadata, and hashes the original source. **Secret and personal-data redaction is not implemented. Use synthetic data only; do not index real incident documents yet.**

## Simulated incident evidence

The JSON files in `corpus/telemetry` stand in for read-only alert, metrics, and Splunk searches. The PAY-QUEUE-LAG, DB-POOL-SATURATION, and CACHE-MISS-SURGE fixtures include time-bounded searches with aggregate result counts and a few representative timestamped events. They are not a complete log archive or a live Splunk connection.

To avoid treating an older fixture as evidence for a new alert of the same type, the agent attaches a fixture only when the chat explicitly names its `snapshot_id` or supplies a matching alert ID, service, region, and exact `fired_at` timestamp. For example:

```text
Alert ID: PAY-QUEUE-LAG
Service: checkout-worker
Fired at: 2026-10-18T14:22:00Z
Region: ca-central-1
```

All other alerts use the incident details supplied in chat, plus the indexed runbooks and architecture documents. Past postmortems can help compare incidents, but are not proof of a new incident's root cause.

## Freshness

Indexing is manual and currently re-indexes the corpus, replacing vectors by document ID. Content hashes are stored in metadata, but incremental hash comparison, scheduled sync, and freshness SLA are not implemented. Superseded documents remain available for explicit historical queries and are excluded from ordinary retrieval. A future connector could target a 15-minute refresh SLA; that is not a current guarantee.

## Chunking and embeddings

The implementation uses heading-aware child chunks with a 450-token target and 50-token overlap. It avoids crossing heading/section boundaries, preserves fenced code blocks and tables as units, and keeps list items intact. Each chunk carries `doc_id`, concise heading-based `section_path`, `service`, `environment`, `version`, `owner`, `status`, review timestamp, source path, and content hash. Citations use `doc_id#section_path`.

The implementation uses LangChain `OpenAIEmbeddings` with OpenAI `text-embedding-3-small` (1536 dimensions), plus `pinecone-text` BM25 sparse vectors. The BM25 encoder is fitted and persisted locally from this corpus when indexing. Retrieval scales dense/sparse values with an initial alpha of 0.65; tune it against the labeled set rather than treating it as an accuracy guarantee. Telemetry JSON is deliberately not embedded; the agent reads it through a local read-only fixture tool.

## Retrieval and answer policy

Before each response, a small model call routes the **latest user message** to incident triage, factual document lookup or prevention, or an out-of-scope reply. Triage answers use the likely-root-cause and possible-fix format when supported; factual and prevention questions receive a direct cited answer. Lookup answers must include an exact excerpt from each cited source; the app checks those excerpts before showing the answer. If the documents omit an exact key, procedure, or other requested detail, the answer says so and directs the user to the project admins. If no relevant support is found, the app says the information is not provided in the sources it can access and directs the user to the project admins. Clearly unrelated questions receive a short scope message. Ambiguous operational messages continue to triage so incident details are not dismissed.

Pinecone stores hybrid dense+sparse chunk vectors. The project's `LangChainHybridRetriever` implements LangChain's `BaseRetriever` interface and exposes the existing Pinecone hybrid query as LangChain `Document` results; the indexing path still uses the Pinecone SDK to preserve the existing vector format. Retrieval requests top 20 results, filters by service (while retaining shared `platform` docs) and environment when known, and excludes superseded procedures unless the question explicitly asks about old guidance. The current version does not yet merge adjacent chunks or use a separate reranker. LangChain `ChatOpenAI` produces structured responses; the response contract allows citations only to retrieved source sections and the selected telemetry snapshot, and unsupported citations are dropped. It asks for clarification when alert/service context is missing or retrieval returns no evidence.

This uses LangChain's model and retriever interfaces without adding a LangChain agent loop or LangGraph. The `langchain-openai` dependency is pinned to a Python 3.9-compatible release because this project currently runs on Python 3.9.

To inspect the LangChain retriever directly from the project environment:

```python
from incident_copilot.runtime import build_agent

agent = build_agent()
documents = agent.retriever.as_retriever(
    service="payment-adapter", environment="production"
).invoke("What triggers the provider timeout alert?")
print(documents[0].page_content)
print(documents[0].metadata["section_path"])
```

Every operational claim should cite one or more retrieved source sections. Separate documented procedure from observed telemetry. If evidence is insufficient, the alert is ambiguous, or sources conflict, the assistant must ask a clarifying question or recommend escalation. The initial agent's telemetry tools are read-only mock fixtures; any future production action requires explicit human approval and a separate authorization design.

The triage summary states a cited likely cause and possible documented fix when both are supported. It distinguishes historical postmortem resolutions from current actions, shows diagnostic checks and recovery options separately, and asks focused questions when it cannot establish a cause or safe recovery path. Recovery options describe required human approval; the assistant does not execute them.

## Evaluation

`evaluation/questions.yaml` contains 28 hand-authored cases with expected source sections, required answer points, abstention expectations, and fixture references. `scripts/evaluate_retrieval.py` reports source-section recall@20, query hit rate@20, and MRR@20 against Pinecone.

`scripts/evaluate_answers.py` runs eight varied cases by default (Q02, Q03, Q13, Q17, Q18, Q20, Q26, Q27), or all 28 with `--all`. The default set includes a factual alert-threshold lookup, a recurrence-prevention question, and an unavailable-detail question. For each case it runs the real retrieval and answer pipeline, then asks an OpenAI judge to check whether **every material claim in each factual statement is supported by that statement's cited source text and incident facts**. A statement with no citation or an invalid reference fails automatically. It also scores citation validity, factual-statement citation coverage, expected answer points, forbidden claims, expected-source citation recall, and whether the requested answer/clarification/escalation/abstention behavior occurred. The report includes the answer, per-statement verdicts, judge reasons, and aggregate scores in `artifacts/answer_evaluation.json`.

The **faithfulness target is at least 90%** supported factual statements across the evaluated cases. The **latency ceiling is p95 at most 15 seconds** for `agent.triage` (retrieval plus answer generation); grading and browser rendering are excluded. p95 uses the nearest-rank method. An eight-case run is a smoke evaluation, not strong statistical evidence; use all 28 cases and manually review disputed judge verdicts before making an accuracy claim. The judge defaults to `gpt-4o` and can be changed with `OPENAI_JUDGE_MODEL` or `--judge-model`; its verdicts are estimates rather than independent ground truth. This evaluation does not yet score tool selection or compare retrieval configurations.

## Setup and run

1. Use Python 3.9 or newer; Python 3.9 is end-of-life, so a supported release is recommended.
2. From this folder, create an environment and install dependencies:

	```bash
	python3 -m venv .venv
	source .venv/bin/activate
	pip install -e ".[dev]"
	```

3. Copy `.env.example` to `.env` and set `OPENAI_API_KEY` and `PINECONE_API_KEY`.
4. Create a Pinecone index named `incident-runbook-copilot` with **1536 dimensions** and **dotproduct** metric. The script does not create cloud resources.
5. Index the synthetic document corpus and fit the BM25 encoder:

	```bash
	python scripts/index_corpus.py
	```

6. Start the Streamlit app:

	```bash
	streamlit run app.py
	```

Start a chat with all available incident details, such as the alert ID, symptoms, service, environment, time window, recent changes, and telemetry. You can also paste alert JSON. If the assistant asks a clarifying question, answer in the chat input; the next triage pass includes the original report, the question, and your reply. Use **New chat** for a separate incident or independent question, then reopen older chats from the sidebar. The sidebar can delete one chat or all chats after confirmation; deleting an open chat clears it from the screen. Chat transcripts are saved as local, unencrypted JSON files in `artifacts/chats/` and are shared by anyone using this local app; they are not stored in Pinecone. Deleted chats cannot be recovered from the app. The app reads service and environment from pasted JSON, labeled fields, or a recognized service name in the incident text. If the index has no applicable documents, the app reports that retrieval gap instead of asking you to repeat the context.

7. Run the retrieval evaluation after indexing:

	```bash
	python scripts/evaluate_retrieval.py
	```

8. Run the generated-answer evaluation (this makes additional OpenAI model calls):

	```bash
	python scripts/evaluate_answers.py
	python scripts/evaluate_answers.py --all
	```

The index command sends the synthetic document chunks to OpenAI for embeddings and stores vectors in Pinecone. The Streamlit agent also sends retrieved evidence and selected telemetry snapshots to the configured OpenAI model. Inspect provider settings and data handling before using any non-synthetic content.

## Tests

```bash
pytest
```

## Suggested build order

1. Add source-approved secret/PII redaction before any real-document ingestion.
2. Add document-level incremental indexing, stale-source checks, and index schema validation.
3. Compare dense-only, sparse-only, and hybrid retrieval against the evaluation set.
4. Expand answer evaluation with independently reviewed verdicts and adversarial prompt-injection cases.
5. Add production-grade read-only telemetry connectors only after access controls and audit logging are defined.
