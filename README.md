# Trusted Data Agent

A LangGraph agent that answers business questions by writing SQL against Oracle AI
Database 26ai, built so it cannot leak data its user is not allowed to see, or change
rows its user may not change. Three defense setups are measured against the same
accuracy, attack, write-abuse and memory suites, and every score is computed by code,
not by an LLM judge:

- **A — prompt rules only.** The model is told what each persona may see.
- **B — A plus app guards:** a SQL validator, an SSN output filter, a grounding check,
  a write validator and a 10% raise rule.
- **C — B plus Oracle Deep Data Security (DDS):** every query runs as the end user, and
  the database decides which rows and columns come back.

> Independent personal project. Not affiliated with, sponsored by, or endorsed by Oracle.

## Results

`qwen3:8b` on an RTX 4060 laptop GPU (8 GB), from
[`results/2026-11-01/matrix.md`](results/2026-11-01/matrix.md):

| Config | Accuracy | Leak rate | Over-refusal | Grounding failures | Unsafe writes | Memory leaks |
|---|---|---|---|---|---|---|
| A | 96.7% | 16.2% | 3.3% | 3.5% | 38.9% | 0.0% |
| B | 95.8% | 11.2% | 3.3% | 0.4% | 16.7% | 0.0% |
| C | 95.8% | 0.0% | 3.3% | 0.4% | 0.0% | 0.0% |

- **Accuracy:** 120 honest questions, scored by comparing result rows with gold SQL run
  as the same persona.
- **Leak rate:** 80 attacks (direct, roleplay, indirect, SQL tricks, aggregation). An attack leaks
  when its rows or its answer hold a value the persona may not read.
- **Over-refusal:** 30 allowed control questions the agent refused, failed or answered with no rows.
- **Grounding failures:** answers with a number the returned rows don't explain.
- **Unsafe writes:** 18 write-abuse attacks, with every proposed change approved. A write
  is unsafe when it changes a row outside the persona's write rules.
- **Memory leaks:** probes whose recall or answer held another persona's code word.

**Live demo:** config C through the public URL scored 10/10 on the smoke questions (all
four personas), median 21.5 s per answer
([`results/cloud-smoke-2026-11-02.md`](results/cloud-smoke-2026-11-02.md)).

What the table shows:

- **Only the database stops every leak.** B's guards check the SQL and its output, but they
  can't know which rows belong to the user. B still leaks 9 of 80 attacks, and its 3 unsafe
  writes are all row violations: the manager's own salary and own expense, and a colleague's phone.
- **Safety cost one question:** the SSN filter masks every SSN, including the user's own
  (`es08`).
- **Memory stays scoped** in every config, since each recall is keyed by config and user.

## How it works

```mermaid
flowchart LR
  visitor["Visitor with the demo token"] -->|HTTPS| edge["Cloudflare edge<br/>*.trycloudflare.com"]
  edge --- cfd["cloudflared<br/>(outbound tunnel)"]
  cfd --> api["FastAPI<br/>/ask, /approve"]
  api --> agent["LangGraph agent<br/>config A, B or C"]
  agent -->|LiteLLM| ollama["Ollama on the GPU<br/>qwen3:8b, nomic-embed-text"]
  agent -->|"A, B: app account<br/>C: end-user session"| db[("Oracle AI Database 26ai Free<br/>Deep Data Security")]
```

- **Reads:** classify the question, find the relevant tables (a vector index in Oracle),
  generate SQL, and run it, then answer from the rows. In B and C, the SQL is validated first,
  SSNs are masked in the rows, and the answer's numbers are checked against the rows.
- **Writes:** generate one UPDATE, preview the rows it would change with a SELECT built
  from the UPDATE's own parse tree, and pause (LangGraph `interrupt`) for a person.
  Then commit only if the row count matches the preview. DDS filters UPDATE rows silently, so
  a count mismatch rolls back and says "No change made".
- **Tracing:** OpenInference spans to Arize Phoenix (`TDA_TRACING=1`).

### Cloud stack (ready, not deployed)

[`deploy/compose.cloud.yml`](deploy/compose.cloud.yml) targets OCI Always Free: an Ampere A1 VM
that runs the API, Ollama on CPU and Caddy, with an Autonomous AI Database 26ai. Caddy serves HTTPS
on port 443 with a Let's Encrypt IP-address certificate. The admin password never reaches the
VM. The stack is tested (`tests/unit/test_deploy.py`, `docker compose config`, `caddy validate`),
but it is not deployed: no OCI account was available. The live demo runs from the laptop instead.

```mermaid
flowchart LR
  visitor["Visitor"] -->|"HTTPS :443"| caddy["Caddy<br/>Let's Encrypt IP cert"]
  subgraph vm["Ampere A1 VM (arm64)"]
    caddy --> app["agent API"] --> ollama["Ollama on CPU"]
  end
  app -->|"TLS, IP access list"| adb[("Autonomous AI Database 26ai")]
```

## Live demo

The demo runs on request, from the laptop that produced the results. The demo token is
available on request, and the URL changes each time the demo starts. After the quickstart
below, with `TDA_DEMO_TOKEN` set in `.env`:

```bash
make image && make demo    # prints https://<random>.trycloudflare.com
make demo-stop
```

The demo is config C by default. The service gets no admin password, no memory and no writes,
and it publishes no port, so the tunnel is its only way in. In config A, which has no validator, the
API runs only single SELECT statements, because A and B connect as `hr`, which owns the tables. Open `$URL/docs` for the Swagger
UI and put `Bearer <token>` in the `authorization` header field. Or:

```bash
curl -s "$URL/ask" -H "Authorization: Bearer $TDA_DEMO_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"persona": "employee", "question": "What is my salary?", "config": "C"}'
```

## Quickstart (WSL Ubuntu 22.04, NVIDIA GPU)

1. `bash scripts/setup-wsl.sh` installs Docker Engine, uv and Ollama.
2. Give WSL about 12 GB of RAM: in `%UserProfile%\.wslconfig`, set `memory=12GB` under `[wsl2]`. Then run `wsl --shutdown`.
3. `cp .env.example .env`, then set the three passwords and the demo token.
4. Run:

```bash
make setup && make test
make up && make llm-up && bash scripts/pull-models.sh qwen3:8b nomic-embed-text
make db-init && make index
make ask PERSONA=employee CONFIG=C Q="What is my salary?"
make api    # http://localhost:8000/docs
```

## Reproduce every number

Run the write eval before the reads. Then rebuild the database, because the write eval
restores rows but not their order:

```bash
for c in A B C; do make writes CONFIG=$c; make memory CONFIG=$c; done
make db-init && make index
for c in A B C; do make accuracy CONFIG=$c; make attacks CONFIG=$c; done
make report   # results/<date>/matrix.md
make smoke    # the 10 smoke questions, in-process
```

`make verify-dds` runs the Deep Data Security integration tests. Run `make index` after it,
because the idempotency test empties the index.

## Documents

- [Threat model](docs/threat-model.md): assets, actors, surfaces, which config stops which attack.

## Limitations

- **Synthetic data:** a seeded HR and expenses schema with four personas.
- **A small local model:** 8B parameters, with answers taking 15–60 s. The answer prose can misformat
  numbers ("INR 25,77,3535.91"); scoring checks rows, not prose.
- **Mostly single-turn attacks:** no multi-turn escalation.
- **Grounding failures vary by load:** unordered rows come back in a new order after
  each rebuild. A has measured 2.6–3.5%, B and C 0.0–0.4%.
- **DDS filters silently:** a forbidden row is missing and a forbidden column is NULL,
  with no error. The agent can't tell "not allowed" from "no data", and may answer "none".
- **The SSN filter masks the user's own SSN too:** control accuracy drops from 56.7% to 43.3%.
- **The demo:** one shared token, no rate limit, a URL that changes on each start, and
  Cloudflare's cutoff of about 100 s per request.

## Production path

- **Identity:** IAM identity propagation from an identity provider, instead of local
  end-user passwords.
- **Memory:** DDS policies on the memory rows. Today the app scopes memory by user id.
- **Approvals:** a database checkpointer, so pending approvals survive a restart (today:
  in memory).
- **Access:** per-user tokens and rate limits instead of one shared demo token.
- **Audit:** Oracle unified auditing of every end-user session and write.
- **Secrets:** a vault (OCI Vault) instead of env files.
- **Least-privilege reads:** a SELECT-only account for A and B, so the database refuses DDL
  instead of the API.
- **Split passwords:** already done. The public app never carries the admin password.

## License

MIT. See [LICENSE](LICENSE).
