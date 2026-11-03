"""Trusted Data Agent."""

import os

# LiteLLM downloads a model price list from GitHub on import unless told otherwise. On networks
# where GitHub is slow, or where IPv4 is missing, that stalls every import; the bundled copy is enough.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
