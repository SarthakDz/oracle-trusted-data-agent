"""Runtime settings, read from the environment and from .env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LAYA_HUB = "convaiinnovations/laya"  # the published English checkpoint (repo root)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    oracle_dsn: str = "localhost:1521/FREEPDB1"
    # The admin account: SYS (as SYSDBA) on Free, ADMIN on Autonomous AI Database. Only dbinit and the
    # admin tests use it, so the app runs without ORACLE_PWD. The Oracle container reads the same variable.
    oracle_admin_user: str = "sys"
    oracle_pwd: str | None = None
    # The schema users the app connects as (HR, TDA_MEMORY).
    app_password: str = Field(validation_alias="TDA_APP_PASSWORD")
    end_user_password: str = Field(validation_alias="TDA_END_USER_PASSWORD")
    ollama_base: str = "http://localhost:11434"
    agent_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"
    # Thinking runs reach ~55 s at p95; the timeout guards against hangs, not slow answers.
    llm_timeout_s: float = 300.0
    # Ollama's default 4096-token window let long thinking runs shift out the start of the prompt.
    # 8192 fits beside qwen3:8b in 8 GB of VRAM; the cap stops a runaway run before the window fills.
    llm_num_ctx: int = 8192
    llm_max_tokens: int = 7000
    phoenix_endpoint: str = "http://localhost:6006/v1/traces"
    tracing: bool = Field(False, validation_alias="TDA_TRACING")
    # On-disk model reply cache for evals (make accuracy sets it); None = every call goes to the model.
    llm_cache_dir: str | None = Field(None, validation_alias="TDA_LLM_CACHE")
    # Laya decision model (tda.decisions, `uv sync --extra laya`). Zero-shot it lost to the qwen3 prompt; fine-tuned
    # it tied (97.1%), but its misses refuse legitimate requests (results/2026-10-31/decisions.md), so "llm" stays
    # the default. Device None = Laya picks (CUDA first).
    classifier: str = "llm"  # "llm" or "laya"
    laya_model: str = LAYA_HUB  # or the directory of a fine-tuned checkpoint (laya-train --out)
    laya_device: str | None = None
    # Per-user memory (tda.memory, schema TDA_MEMORY). Off by default: the read and write evals must not
    # see earlier cases; the memory eval and the API turn it on.
    memory: bool = Field(False, validation_alias="TDA_MEMORY")
    # The API's shared demo token (synthetic data only); unset = every protected endpoint answers 503.
    demo_token: str | None = Field(None, validation_alias="TDA_DEMO_TOKEN")
    # Approved writes commit through the API only when this is on (config C only). Off for the public
    # demo: one visitor holding the shared token would change the demo data for everyone after.
    demo_writes: bool = Field(False, validation_alias="TDA_DEMO_WRITES")


@lru_cache
def get_settings() -> Settings:
    return Settings()
