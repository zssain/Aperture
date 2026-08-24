"""Model-card generation from registries and measured metrics only.

The PDF export is a small, dependency-free renderer built directly on PDF operators. It
lays the card out as a branded, professional document — the Aperture mark, section
headings, bordered tables, and vector charts (a reliability diagram and the coverage
histogram). Every drawn value is a real measured number handed in via the card; nothing
here fabricates a data point.
"""

import math
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
    calibration = metrics.get("calibration", {}) if isinstance(metrics, dict) else {}
    model_a = calibration.get("model_a", {}) if isinstance(calibration, dict) else {}
    coverage = metrics.get("coverage", {}) if isinstance(metrics, dict) else {}
    overrides = metrics.get("overrides", {}) if isinstance(metrics, dict) else {}
    return {
        "title": "APERTURE model card",
        "generated_at": metrics.get("data_as_of") if isinstance(metrics, dict) else None,
        "features": feature_names,
        "measured_metrics": measured,
        "not_yet_measured": not_yet,
        # Chart / narrative inputs (present only when the endpoint supplies full metrics).
        "reliability": list(model_a.get("reliability", [])) if isinstance(model_a, dict) else [],
        "coverage_histogram": list(coverage.get("histogram", []))
        if isinstance(coverage, dict)
        else [],
        "overrides_by_reason": dict(overrides.get("by_reason", {}))
        if isinstance(overrides, dict)
        else {},
    }


# --------------------------------------------------------------------------- #
# PDF rendering — a minimal, dependency-free vector toolkit.
# --------------------------------------------------------------------------- #

_PAGE_W, _PAGE_H = 612.0, 792.0
_MARGIN = 50.0
_CONTENT_W = _PAGE_W - 2 * _MARGIN

# Brand palette (from frontend/public/brand/aperture-icon.svg).
_GREEN = (0.063, 0.620, 0.467)  # #109E77
_NAVY = (0.059, 0.114, 0.180)  # #0F1D2E
_INK = (0.13, 0.16, 0.20)
_GREY = (0.42, 0.45, 0.50)
_RULE = (0.80, 0.83, 0.86)
_ROW = (0.955, 0.965, 0.972)
_PANEL = (0.972, 0.980, 0.986)
_WHITE = (1.0, 1.0, 1.0)

# Approximate Helvetica advance widths (fraction of font size) for layout/alignment.
_AVG = 0.50
_AVG_BOLD = 0.54


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text_width(text: str, size: float, bold: bool = False) -> float:
    return len(text) * size * (_AVG_BOLD if bold else _AVG)


def _wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and _text_width(trial, size, bold) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)
    return lines


class _Canvas:
    """Accumulates PDF content operators and paginates into page streams."""

    def __init__(self) -> None:
        self.pages: list[str] = []
        self._ops: list[str] = []
        self.y = _PAGE_H - _MARGIN
        self.page_no = 1

    # -- raw state -------------------------------------------------------- #
    def _op(self, op: str) -> None:
        self._ops.append(op)

    def _fill(self, color: tuple[float, float, float]) -> None:
        self._op(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg")

    def _stroke(self, color: tuple[float, float, float]) -> None:
        self._op(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG")

    def line_width(self, width: float) -> None:
        self._op(f"{width:g} w")

    # -- primitives ------------------------------------------------------- #
    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: tuple[float, float, float] | None = None,
        stroke: tuple[float, float, float] | None = None,
        width: float = 0.6,
    ) -> None:
        if fill is not None:
            self._fill(fill)
        if stroke is not None:
            self._stroke(stroke)
            self.line_width(width)
        self._op(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        self._op("B" if fill is not None and stroke is not None else ("f" if fill else "S"))

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: tuple[float, float, float] = _RULE,
        width: float = 0.6,
        dashed: bool = False,
    ) -> None:
        self._stroke(color)
        self.line_width(width)
        if dashed:
            self._op("[3 3] 0 d")
        self._op(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")
        if dashed:
            self._op("[] 0 d")

    def polygon(self, points: list[tuple[float, float]], fill: tuple[float, float, float]) -> None:
        if not points:
            return
        self._fill(fill)
        start = points[0]
        self._op(f"{start[0]:.2f} {start[1]:.2f} m")
        for px, py in points[1:]:
            self._op(f"{px:.2f} {py:.2f} l")
        self._op("h f")

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 9.0,
        bold: bool = False,
        color: tuple[float, float, float] = _INK,
    ) -> None:
        self._fill(color)
        font = "F2" if bold else "F1"
        self._op(
            f"BT /{font} {size:g} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({_esc(s)}) Tj ET"
        )

    def text_right(self, x_right: float, y: float, s: str, size: float = 9.0, **kw: Any) -> None:
        self.text(x_right - _text_width(s, size, bool(kw.get("bold"))), y, s, size, **kw)

    def text_center(self, x_center: float, y: float, s: str, size: float = 9.0, **kw: Any) -> None:
        self.text(x_center - _text_width(s, size, bool(kw.get("bold"))) / 2, y, s, size, **kw)

    # -- flow / pagination ------------------------------------------------ #
    def space(self, amount: float) -> None:
        self.y -= amount

    def ensure(self, needed: float) -> None:
        if self.y - needed < _MARGIN + 24:
            self.new_page()

    def new_page(self) -> None:
        self._footer()
        self.pages.append("\n".join(self._ops))
        self._ops = []
        self.page_no += 1
        self.y = _PAGE_H - _MARGIN

    def finish(self) -> list[str]:
        self._footer()
        self.pages.append("\n".join(self._ops))
        self._ops = []
        return self.pages

    def _footer(self) -> None:
        self.line(_MARGIN, _MARGIN + 14, _PAGE_W - _MARGIN, _MARGIN + 14, _RULE, 0.5)
        self.text(
            _MARGIN,
            _MARGIN + 4,
            "Aperture - model & policy oversight. UNCALIBRATED risk model; PD ranks risk, "
            "not literal probability.",
            6.5,
            color=_GREY,
        )
        self.text_right(_PAGE_W - _MARGIN, _MARGIN + 4, f"Page {self.page_no}", 6.5, color=_GREY)

    # -- brand mark ------------------------------------------------------- #
    def aperture_mark(self, cx: float, cy: float, size: float) -> None:
        """Draw the four-bar Aperture aperture mark (one green blade, three navy)."""
        # Base blade rect in the 0..100 SVG viewbox, rotated 0/90/180/270 about (50,50).
        base = [(20.0, 28.0), (56.0, 28.0), (56.0, 40.0), (20.0, 40.0)]
        scale = size / 100.0
        for index, angle in enumerate((0, 90, 180, 270)):
            radians = math.radians(angle)
            cos_a, sin_a = math.cos(radians), math.sin(radians)
            corners: list[tuple[float, float]] = []
            for sx, sy in base:
                dx, dy = sx - 50.0, sy - 50.0
                rx = 50.0 + dx * cos_a - dy * sin_a
                ry = 50.0 + dx * sin_a + dy * cos_a
                # Map SVG (y-down) to PDF (y-up), centred on (cx, cy).
                corners.append((cx + (rx - 50.0) * scale, cy - (ry - 50.0) * scale))
            self.polygon(corners, _GREEN if index == 0 else _NAVY)

    # -- tables ----------------------------------------------------------- #
    def table(
        self,
        cols: list[tuple[str, float]],
        rows: list[list[str]],
        wrap_last: bool = False,
    ) -> None:
        x0 = _MARGIN
        header_h = 18.0
        pad = 5.0
        widths = [w for _, w in cols]

        def draw_header() -> None:
            self.rect(x0, self.y - header_h, _CONTENT_W, header_h, fill=_NAVY)
            cx = x0
            for (label, _), w in zip(cols, widths, strict=True):
                self.text(cx + pad, self.y - header_h + 5.5, label, 8.0, bold=True, color=_WHITE)
                cx += w
            self.y -= header_h

        self.ensure(header_h + 30)
        draw_header()
        for r, row in enumerate(rows):
            # Row height depends on the wrapped final cell when wrap_last is set.
            last_lines = (
                _wrap(row[-1], 8.0, widths[-1] - 2 * pad) if wrap_last else [row[-1] if row else ""]
            )
            row_h = max(15.0, 6.0 + len(last_lines) * 9.5)
            if self.y - row_h < _MARGIN + 26:
                self.new_page()
                draw_header()
            if r % 2 == 0:
                self.rect(x0, self.y - row_h, _CONTENT_W, row_h, fill=_ROW)
            cx = x0
            for c, (value, w) in enumerate(zip(row, widths, strict=True)):
                ty = self.y - 11.0
                if wrap_last and c == len(row) - 1:
                    for line in last_lines:
                        self.text(cx + pad, ty, line, 8.0, color=_INK)
                        ty -= 9.5
                else:
                    self.text(cx + pad, ty, value, 8.0, color=_INK)
                cx += w
            self.line(x0, self.y - row_h, x0 + _CONTENT_W, self.y - row_h, _RULE, 0.5)
            self.y -= row_h
        # Outer border.
        self.rect(x0, self.y, _CONTENT_W, 0.0, stroke=None)

    # -- charts ----------------------------------------------------------- #
    def reliability_chart(self, points: list[dict[str, Any]], x: float, y_top: float) -> float:
        w, h = 250.0, 128.0
        plot_x, plot_y = x + 34.0, y_top - h + 24.0
        plot_w, plot_h = w - 44.0, h - 40.0
        # Panel + frame.
        self.rect(x, y_top - h, w, h, fill=_PANEL, stroke=_RULE, width=0.6)
        self.rect(plot_x, plot_y, plot_w, plot_h, stroke=_RULE, width=0.6)
        # Gridlines + ticks (0, 0.5, 1.0 on both axes).
        for t in (0.0, 0.5, 1.0):
            gy = plot_y + t * plot_h
            gx = plot_x + t * plot_w
            if 0.0 < t < 1.0:
                self.line(plot_x, gy, plot_x + plot_w, gy, _RULE, 0.4)
            self.text_right(plot_x - 4, gy - 3, f"{t:.1f}", 6.5, color=_GREY)
            self.text_center(gx, plot_y - 10, f"{t:.1f}", 6.5, color=_GREY)
        # Perfect-calibration diagonal (dashed reference).
        self.line(plot_x, plot_y, plot_x + plot_w, plot_y + plot_h, _GREY, 0.7, dashed=True)

        def to_xy(pred: float, obs: float) -> tuple[float, float]:
            return (
                plot_x + max(0.0, min(1.0, pred)) * plot_w,
                plot_y + max(0.0, min(1.0, obs)) * plot_h,
            )

        # Observed-vs-predicted curve (green) with markers.
        ordered = sorted(points, key=lambda p: float(p.get("predicted", 0.0)))
        prev: tuple[float, float] | None = None
        for point in ordered:
            px, py = to_xy(float(point.get("predicted", 0.0)), float(point.get("observed", 0.0)))
            if prev is not None:
                self.line(prev[0], prev[1], px, py, _GREEN, 1.4)
            prev = (px, py)
        for point in ordered:
            px, py = to_xy(float(point.get("predicted", 0.0)), float(point.get("observed", 0.0)))
            self.rect(px - 1.7, py - 1.7, 3.4, 3.4, fill=_NAVY)
        # Axis titles + legend.
        self.text_center(plot_x + plot_w / 2, plot_y - 20, "Predicted PD", 7.0, color=_GREY)
        self.text(x + 6, plot_y + plot_h / 2 - 18, "Observed", 7.0, color=_GREY)
        self.text(x + 6, plot_y + plot_h / 2 - 27, "default", 7.0, color=_GREY)
        self.line(x + 8, y_top - 12, x + 20, y_top - 12, _GREEN, 1.4)
        self.text(x + 23, y_top - 14.5, "Reliability", 6.5, color=_GREY)
        self.line(x + 74, y_top - 12, x + 86, y_top - 12, _GREY, 0.7, dashed=True)
        self.text(x + 89, y_top - 14.5, "Perfect calibration", 6.5, color=_GREY)
        return y_top - h

    def histogram(
        self, bins: list[dict[str, Any]], x: float, y_top: float, w: float, title: str
    ) -> float:
        h = 128.0
        plot_x, plot_y = x + 8.0, y_top - h + 26.0
        plot_w, plot_h = w - 16.0, h - 46.0
        self.rect(x, y_top - h, w, h, fill=_PANEL, stroke=_RULE, width=0.6)
        self.text(x + 8, y_top - 14, title, 8.0, bold=True, color=_NAVY)
        counts = [int(b.get("n", 0)) for b in bins]
        peak = max(counts) if counts else 0
        self.line(plot_x, plot_y, plot_x + plot_w, plot_y, _RULE, 0.6)
        if peak <= 0:
            mid = plot_y + plot_h / 2
            self.text_center(x + w / 2, mid, "No applications yet", 7.5, color=_GREY)
            return y_top - h
        slot = plot_w / max(1, len(bins))
        bar_w = slot * 0.66
        for index, b in enumerate(bins):
            count = int(b.get("n", 0))
            bar_h = (count / peak) * plot_h
            bx = plot_x + index * slot + (slot - bar_w) / 2
            if count > 0:
                self.rect(bx, plot_y, bar_w, bar_h, fill=_GREEN)
                self.text_center(bx + bar_w / 2, plot_y + bar_h + 2.5, str(count), 6.0, color=_INK)
            label = str(b.get("range", "")).split("-")[0]
            if index % 2 == 0:
                self.text_center(bx + bar_w / 2, plot_y - 9, label, 6.0, color=_GREY)
        self.text_center(x + w / 2, plot_y - 19, "Coverage score", 7.0, color=_GREY)
        return y_top - h


def _metric_label(path: str) -> str:
    return " / ".join(part.replace("_", " ").strip().title() for part in path.split(".") if part)


def _fmt(value: Any, digits: int = 4) -> str:
    return "-" if value is None else f"{float(value):.{digits}f}"


def _render(card: dict[str, Any]) -> _Canvas:
    c = _Canvas()

    # --- Header band with the brand mark ---------------------------------- #
    top = _PAGE_H - _MARGIN
    c.aperture_mark(_MARGIN + 13, top - 15, 30)
    c.text(_MARGIN + 34, top - 12, "Aperture", 20.0, bold=True, color=_NAVY)
    c.text(_MARGIN + 34, top - 25, "Model & policy oversight", 8.5, color=_GREY)
    c.text_right(_PAGE_W - _MARGIN, top - 9, "MODEL CARD", 12.0, bold=True, color=_GREEN)
    generated = str(card.get("generated_at") or "")[:10]
    if generated:
        c.text_right(_PAGE_W - _MARGIN, top - 22, f"Generated {generated}", 8.0, color=_GREY)
    c.space(38)
    c.line(_MARGIN, c.y, _PAGE_W - _MARGIN, c.y, _NAVY, 1.2)
    c.space(10)

    for line in _wrap(
        "Model estimates, policy decides. Every numeric metric below is gated: it is shown only "
        "once enough closed outcomes exist to measure it honestly. Metrics without enough data "
        "are listed with the reason they are withheld.",
        9.0,
        _CONTENT_W,
    ):
        c.text(_MARGIN, c.y, line, 9.0, color=_INK)
        c.space(12)
    c.space(8)
    # --- Model performance: reliability chart + measured metrics table ---- #
    c.ensure(180)
    c.text(_MARGIN, c.y, "Model performance", 12.0, bold=True, color=_NAVY)
    c.space(6)
    chart_top = c.y
    reliability = card.get("reliability", [])
    if reliability:
        c.reliability_chart(reliability, _PAGE_W - _MARGIN - 250, chart_top)
        note_x = _MARGIN
        note_w = _CONTENT_W - 262
        c.text(note_x, chart_top - 12, "Reliability diagram", 9.0, bold=True, color=_INK)
        # Drop the cursor below the heading so the paragraph does not render on top of it.
        c.y = chart_top - 14
        for line in _wrap(
            "Predicted PD (x) against the observed default rate (y) per score band. Points on the "
            "dashed line are perfectly calibrated; points above it mean the model under-predicts "
            "risk - the expected shape for a model still labelled UNCALIBRATED.",
            8.0,
            note_w,
        ):
            c.space(11)
            c.text(note_x, c.y, line, 8.0, color=_GREY)
        c.y = min(c.y, chart_top - 128) - 12
    else:
        c.text(_MARGIN, c.y, "Reliability diagram not yet available (needs closed outcomes).", 8.5,
               color=_GREY)
        c.space(14)

    measured = card.get("measured_metrics", {})
    if measured:
        rows = [
            [
                _metric_label(path),
                _fmt(m.get("value")),
                (
                    f"{_fmt(m.get('ci_low'))} - {_fmt(m.get('ci_high'))}"
                    if m.get("ci_low") is not None
                    else "-"
                ),
                str(m.get("n") if m.get("n") is not None else "-"),
            ]
            for path, m in measured.items()
        ]
        c.table(
            [("Metric", 232.0), ("Value", 70.0), ("95% CI", 130.0), ("n", 80.0)],
            rows,
        )
    c.space(10)

    # --- Coverage histogram ---------------------------------------------- #
    histogram = card.get("coverage_histogram", [])
    if histogram:
        c.ensure(168)
        c.text(_MARGIN, c.y, "Evidence coverage distribution", 12.0, bold=True, color=_NAVY)
        c.space(6)
        c.histogram(histogram, _MARGIN, c.y, _CONTENT_W, "Applications by coverage score (0-100)")
        c.space(128 + 8)

    # --- Governance: not-yet-measured ------------------------------------ #
    not_yet = card.get("not_yet_measured", [])
    c.ensure(70)
    c.text(_MARGIN, c.y, "Governance - not yet measured", 12.0, bold=True, color=_NAVY)
    c.space(6)
    if not_yet:
        c.table(
            [("Metric", 150.0), ("Status", 110.0), ("Reason withheld", 252.0)],
            [
                [
                    _metric_label(str(item.get("metric", ""))),
                    str(item.get("status", "")),
                    str(item.get("reason", "")),
                ]
                for item in not_yet
            ],
            wrap_last=True,
        )
    else:
        c.text(_MARGIN, c.y, "Every metric has reached its minimum sample.", 8.5, color=_GREY)
        c.space(12)
    c.space(10)

    # --- Observed features ----------------------------------------------- #
    features = list(card.get("features", []))
    c.ensure(40)
    c.text(_MARGIN, c.y, f"Observed features ({len(features)})", 12.0, bold=True, color=_NAVY)
    c.space(13)
    for line in _wrap(", ".join(features) if features else "None declared.", 8.0, _CONTENT_W):
        c.ensure(12)
        c.text(_MARGIN, c.y, line, 8.0, color=_GREY)
        c.space(10)

    return c


def model_card_pdf(card: dict[str, Any]) -> bytes:
    """Render the model card as a branded, paginated PDF with a valid cross-reference table."""
    pages = _render(card).finish()
    page_count = len(pages)

    # 1 Catalog, 2 Pages, 3 Font F1, 4 Font F2, then per page Page + Contents.
    page_obj_ids = [5 + 2 * i for i in range(page_count)]
    content_obj_ids = [6 + 2 * i for i in range(page_count)]
    kids = " ".join(f"{obj} 0 R" for obj in page_obj_ids)

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    }
    for index, stream_text in enumerate(pages):
        page_id, content_id = page_obj_ids[index], content_obj_ids[index]
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_W:g} {_PAGE_H:g}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        stream = stream_text.encode("latin-1", "replace")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(out)
        out += f"{obj_id} 0 obj\n".encode() + objects[obj_id] + b"\nendobj\n"

    xref_pos = len(out)
    total = len(objects) + 1
    out += f"xref\n0 {total}\n".encode()
    out += b"0000000000 65535 f \n"
    for obj_id in range(1, total):
        out += f"{offsets[obj_id]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)
