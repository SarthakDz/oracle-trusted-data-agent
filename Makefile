# Trusted Data Agent. Run every target from WSL.
# The project path contains a space ("/mnt/f/New folder"), so recipes quote paths.
# The venv lives off /mnt/f because 9p file access from WSL is slow.
export UV_PROJECT_ENVIRONMENT := $(HOME)/.venvs/tda
export UV_PYTHON_DOWNLOADS := never
export PATH := $(HOME)/.local/bin:$(PATH)

.PHONY: setup test up down db-init index api ask verify-dds verify-agent llm-up models bakeoff smoke accuracy attacks writes memory report image image-arm64 live-smoke demo demo-stop

setup:
	uv sync --python python3.10

test:
	uv run pytest -q

up:
	docker compose up -d --wait oracle phoenix

down:
	@# --remove-orphans: the demo and the tunnel come from deploy/compose.demo.yml; never leave the tunnel up
	docker compose down --remove-orphans

db-init:
	uv run python -m tda.dbinit

api: llm-up
	uv run uvicorn tda.api:app --host 0.0.0.0 --port 8000

PERSONA ?= employee
ask: llm-up
	uv run python -m tda.cli --persona "$(PERSONA)" --config "$(CONFIG)" "$(Q)"

index: llm-up
	uv run python -m tda.schema_index

verify-dds:
	uv run pytest -q -m "integration and not llm"

verify-agent: llm-up
	uv run pytest -q -m llm

llm-up:
	@# [::] listens on IPv6 and IPv4 alike: IPv4 loopback breaks in WSL mirrored mode on IPv6-only networks.
	@pgrep -x ollama >/dev/null || (OLLAMA_HOST="[::]:11434" nohup ollama serve > "$(HOME)/.ollama-serve.log" 2>&1 &)
	@echo "ollama on http://localhost:11434 (log: $(HOME)/.ollama-serve.log)"

models:
	bash scripts/pull-models.sh

bakeoff: llm-up
	uv run python -m evals.bakeoff

smoke: llm-up
	uv run python -m evals.smoke

# The response cache makes a re-run reproduce a run exactly (and resume a crashed one).
MODEL ?= qwen3:8b
CONFIG ?= A
accuracy: llm-up
	TDA_LLM_CACHE=.cache/llm uv run python -m evals.accuracy --config "$(CONFIG)" --model "$(MODEL)"

attacks: llm-up
	TDA_LLM_CACHE=.cache/llm uv run python -m evals.attacks --config "$(CONFIG)" --model "$(MODEL)"

# Approves every proposed write, scores the table diff, then restores it (refuses to start on a drifted database).
writes: llm-up
	TDA_LLM_CACHE=.cache/llm uv run python -m evals.writes --config "$(CONFIG)" --model "$(MODEL)"

# Seeds one code word per persona in memory, probes for the others', then forgets them.
memory: llm-up
	TDA_LLM_CACHE=.cache/llm uv run python -m evals.memory --config "$(CONFIG)" --model "$(MODEL)"

report:
	uv run python -m evals.report

# The API image. amd64 runs here; arm64 (the OCI Ampere VM) builds under QEMU
# (once: docker run --privileged --rm tonistiigi/binfmt --install arm64).
image:
	docker buildx build --platform linux/amd64 -t tda-app:dev --load .

image-arm64:
	docker buildx build --platform linux/arm64 -t tda-app:arm64 --load .

# The Day 2 smoke questions through the live API (config C). Gold rows come from the database the
# deployment uses, so export its settings first (the laptop demo: export TDA_DEMO_TOKEN from .env).
live-smoke:
	@test -n "$(URL)" || (echo "set URL, e.g. make live-smoke URL=https://<the demo URL>"; exit 2)
	uv run python -m evals.live_smoke --url "$(URL)"

# The public demo (deploy/compose.demo.yml): the API behind a Cloudflare quick tunnel. Prints the URL,
# which changes on every start. Needs `make image` and TDA_DEMO_TOKEN in .env. Stop it after the demo.
DEMO := docker compose -f docker-compose.yml -f deploy/compose.demo.yml
demo: llm-up
	$(DEMO) up -d --wait demo tunnel
	@for i in $$(seq 1 30); do $(DEMO) logs tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 | grep . && break; sleep 2; done

demo-stop:
	$(DEMO) rm -sf demo tunnel
