"""The public stacks: what reaches the public API and what is exposed.

deploy/compose.cloud.yml is the OCI stack (tested, not deployed); deploy/compose.demo.yml serves
the laptop's API through a Cloudflare quick tunnel.
"""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
STACK = ROOT / "deploy" / "compose.cloud.yml"
DEMO = ROOT / "deploy" / "compose.demo.yml"
PUBLIC = [(STACK, "app"), (DEMO, "demo")]


def _services(path: Path = STACK) -> dict:
    return yaml.safe_load(path.read_text())["services"]


@pytest.mark.parametrize("path, name", PUBLIC)
def test_public_app_gets_no_admin_password(path, name):
    # dbinit runs outside the public app; it runs with the app and end-user passwords only.
    app = _services(path)[name]
    assert "ORACLE_PWD" not in app["environment"] and "env_file" not in app


@pytest.mark.parametrize("path, name", PUBLIC)
def test_public_app_requires_secrets(path, name):
    # Compose refuses to start without them, so the public API can't come up open or half-configured.
    env = _services(path)[name]["environment"]
    for key in ("TDA_DEMO_TOKEN", "TDA_APP_PASSWORD", "TDA_END_USER_PASSWORD"):
        assert ":?" in env[key], key


@pytest.mark.parametrize("path, name", PUBLIC)
def test_public_app_runs_without_memory(path, name):
    # Visitors share personas: shared memory would recall one visitor's questions for another,
    # and writes would let one visitor change the demo data for everyone.
    env = _services(path)[name]["environment"]
    assert "TDA_MEMORY" not in env and "TDA_DEMO_WRITES" not in env


def test_example_env_ships_no_demo_token():
    # Any non-empty token works, so a token printed in a public repo opens the demo to everyone who copies it.
    assert "TDA_DEMO_TOKEN=" in (ROOT / ".env.example").read_text().splitlines()


def test_tunnel_reaches_only_the_demo_api():
    # The demo publishes no port, so the tunnel is its only door (and it never clashes with the dev app's 8000).
    services = _services(DEMO)
    tunnel, demo = services["tunnel"], services["demo"]
    assert "--url http://demo:8000" in tunnel["command"]
    assert "ports" not in tunnel and "ports" not in demo
    assert not tunnel["image"].endswith(":latest")


def test_only_https_is_published():
    published = {name: s.get("ports", []) for name, s in _services().items()}
    assert published.pop("caddy") == ["443:443"]
    # Anything else (the fallback database) binds loopback only: reachable through an SSH tunnel.
    assert all(str(p).startswith("127.0.0.1:") for ports in published.values() for p in ports)


def test_cloud_secrets_are_ignored():
    for path in ("deploy/.env", ".env.cloud"):  # -q takes one path at a time
        subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=True)
    ignored = (ROOT / ".dockerignore").read_text().split()
    assert "deploy" in ignored and ".env.cloud" in ignored
