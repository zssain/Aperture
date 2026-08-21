"""Model-card generation from registries and measured metrics only."""

import json
from typing import Any


def build_model_card(feature_names: list[str], metrics: dict[str, Any]) -> dict[str, Any]:
    measured: dict[str, Any] = {}
    not_yet: list[dict[str, str]] = []

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict) and "status" in value:
            if value["status"] == "MEASURED":
                measured[prefix] = value
            else:
                not_yet.append(
                    {
                        "metric": prefix,
                        "status": value["status"],
                        "reason": str(value.get("reason") or "Not yet measured"),
                    }
                )
        elif isinstance(value, dict):
            for key, child in value.items():
                walk(f"{prefix}.{key}".strip("."), child)

    walk("", metrics)
    return {
        "title": "APERTURE model card",
        "features": feature_names,
        "measured_metrics": measured,
        "not_yet_measured": not_yet,
    }


def model_card_pdf(card: dict[str, Any]) -> bytes:
    text = json.dumps(card, ensure_ascii=True, indent=2).replace("(", "[").replace(")", "]")[:5000]
    stream = f"BT /F1 8 Tf 36 780 Td ({text.replace(chr(10), ' ')}) Tj ET".encode()
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
        ),
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode() + stream + b"\nendstream endobj\n",
        b"trailer << /Root 1 0 R >>\n%%EOF",
    ]
    return b"".join(parts)
