"""Manual performance scatter for student papers. Style follows the lab's FPS–mIoU bubble chart."""

from __future__ import annotations

import hashlib
import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MAIN_COLOR = "#d62728"
OTHER_COLORS = (
    "#1f77b4",
    "#2ca02c",
    "#9467bd",
    "#ff7f0e",
    "#17becf",
    "#8c564b",
    "#e377c2",
    "#bcbd22",
    "#7f7f7f",
    "#393b79",
    "#637939",
    "#8c6d31",
    "#3182bd",
    "#31a354",
    "#756bb1",
)


def mm_to_scatter_s(diameter_mm: float) -> float:
    """Matplotlib scatter `s` is marker width squared, in points (1/72 in)."""
    diameter_pt = float(diameter_mm) / 25.4 * 72.0
    return float(diameter_pt**2)


def _configure_fonts() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42


def _pick_colors(names: list[str], main_index: int) -> list[str]:
    colors: list[str] = []
    used: set[str] = {MAIN_COLOR}
    for index, name in enumerate(names):
        if index == main_index:
            colors.append(MAIN_COLOR)
            continue
        digest = hashlib.sha256(f"{index}:{name}".encode("utf-8")).digest()
        start = digest[0] % len(OTHER_COLORS)
        chosen = OTHER_COLORS[0]
        for offset in range(len(OTHER_COLORS)):
            candidate = OTHER_COLORS[(start + offset) % len(OTHER_COLORS)]
            if candidate not in used:
                chosen = candidate
                break
        used.add(chosen)
        colors.append(chosen)
    return colors


def _sizes(params: list[float | None], default_mm: float) -> list[float]:
    known = [value for value in params if value is not None and value > 0]
    default_s = mm_to_scatter_s(default_mm)
    if not known:
        return [default_s for _ in params]
    low, high = min(known), max(known)
    sizes: list[float] = []
    for value in params:
        if value is None or value <= 0:
            sizes.append(default_s)
            continue
        if high <= low:
            sizes.append(mm_to_scatter_s(max(default_mm, 8.0)))
            continue
        ratio = (value - low) / (high - low)
        diameter = 4.0 + ratio * 14.0
        sizes.append(mm_to_scatter_s(diameter))
    return sizes


def render_scatter(
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    points: list[dict[str, Any]],
    default_marker_mm: float = 5.0,
    fmt: str = "png",
) -> bytes:
    if fmt not in {"png", "pdf"}:
        raise ValueError("fmt must be png or pdf")
    if not points:
        raise ValueError("至少需要一个模型")
    names = [str(item["name"]).strip() or f"模型{index + 1}" for index, item in enumerate(points)]
    xs = [float(item["x"]) for item in points]
    ys = [float(item["y"]) for item in points]
    params = []
    for item in points:
        raw = item.get("params")
        params.append(None if raw is None or raw == "" else float(raw))
    main_index = 0
    for index, item in enumerate(points):
        if item.get("is_main"):
            main_index = index
            break
    colors = _pick_colors(names, main_index)
    sizes = _sizes(params, default_marker_mm)

    _configure_fonts()
    fig, ax = plt.subplots(figsize=(10, 7.2), dpi=160)
    ax.scatter(xs, ys, s=sizes, c=colors, alpha=0.85, edgecolors="black", linewidths=0.6, zorder=3)
    ax.set_xlabel(xlabel or "X", fontsize=16)
    ax.set_ylabel(ylabel or "Y", fontsize=16)
    if title.strip():
        ax.set_title(title.strip(), fontsize=18, fontweight="bold", pad=12)
    x_span = max(max(xs) - min(xs), 1e-6)
    y_span = max(max(ys) - min(ys), 1e-6)
    ax.set_xlim(min(xs) - 0.08 * x_span, max(xs) + 0.08 * x_span)
    ax.set_ylim(min(ys) - 0.08 * y_span, max(ys) + 0.12 * y_span)
    ax.tick_params(labelsize=12)
    ax.grid(True, linestyle="--", alpha=0.45)

    ranked = sorted(zip(names, ys, colors, strict=True), key=lambda row: -row[1])
    list_x = 0.03
    list_y = 0.96
    spacing = min(0.048, 0.72 / max(len(ranked), 1))
    ax.text(
        list_x,
        list_y,
        f"Algorithm          {ylabel or 'Y'}",
        fontsize=11,
        ha="left",
        va="top",
        transform=ax.transAxes,
        fontweight="bold",
    )
    ax.plot(
        [list_x - 0.01, list_x + 0.36],
        [list_y - 0.028, list_y - 0.028],
        transform=ax.transAxes,
        color="black",
        linewidth=0.8,
        clip_on=False,
    )
    for index, (name, y_value, color) in enumerate(ranked):
        current_y = list_y - 0.055 - index * spacing
        if current_y < 0.04:
            break
        ax.scatter(
            [list_x + 0.012],
            [current_y],
            s=90,
            c=[color],
            edgecolors="black",
            linewidths=0.4,
            transform=ax.transAxes,
            clip_on=False,
            zorder=5,
        )
        ax.text(
            list_x + 0.04,
            current_y,
            name,
            fontsize=10,
            ha="left",
            va="center",
            transform=ax.transAxes,
        )
        ax.text(
            list_x + 0.28,
            current_y,
            f"{y_value:.2f}",
            fontsize=10,
            ha="left",
            va="center",
            transform=ax.transAxes,
        )

    fig.tight_layout(rect=[0.04, 0.04, 0.98, 0.96])
    buffer = io.BytesIO()
    fig.savefig(buffer, format=fmt, bbox_inches="tight", dpi=200 if fmt == "png" else None)
    plt.close(fig)
    return buffer.getvalue()
