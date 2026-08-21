import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"VITE_[A-Z0-9_]*(?:SECRET|PASSWORD|PRIVATE_KEY|API_KEY)\s*="),
)


def test_repository_and_frontend_sources_contain_no_literal_credentials() -> None:
    checked = [ROOT / "backend/app", ROOT / "frontend/src", ROOT / "deploy", ROOT / ".env.example"]
    for target in checked:
        paths = target.rglob("*") if target.is_dir() else [target]
        for path in paths:
            if not path.is_file():
                continue
            text = path.read_text(errors="ignore")
            assert not any(pattern.search(text) for pattern in PATTERNS), str(path)
