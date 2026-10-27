import os

# Models are instantiated at import time, so the key must exist before any
# `src.*` module is imported.
os.environ.setdefault("MISTRAL_API_KEY", "test-key")
