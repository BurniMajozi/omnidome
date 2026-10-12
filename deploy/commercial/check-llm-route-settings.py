"""Print model-routing settings only; never credentials or the full environment."""
import json
import os
print(json.dumps({name:os.getenv(name) for name in ("OPENROUTER_MODEL","OPENROUTER_FALLBACK_MODELS")}))
