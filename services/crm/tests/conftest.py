import importlib.metadata
import sys
from unittest.mock import MagicMock

orig_version = importlib.metadata.version

def mock_version(pkg):
    if pkg == "email-validator":
        return "2.1.0"
    return orig_version(pkg)

importlib.metadata.version = mock_version

if "email_validator" not in sys.modules:
    ev = MagicMock()
    ev.validate_email = lambda email, **kwargs: MagicMock(normalized=email, email=email)
    sys.modules["email_validator"] = ev
