"""README figure: forecast error relative to the naive forecast, v1 (price levels) vs v2 (returns).

Input: docs/figures/model_benchmark.csv (MAE as % of last price, walk-forward CV).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

FIG = Path(__file__).resolve().parent.parent / "docs" / "figures"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
V1, V2 = "#eb6834", "#2a78d6"   # categorical slots 2 and 1

df = pd.read_csv(FIG / "model_benchmark.csv").set_index("asset")
df["v1_ratio"] = df["v1_level"] / df["naive"]
df["v2_ratio"] = df["v2_return"] / df["naive"]
df = df.sort_values("v1_ratio")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
fig, ax = plt.subplots(figsize=(8, 4.2), dpi=200, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
y = range(len(df))
for i, (_, r) in enumerate(df.iterrows()):
    ax.plot([r.v2_ratio, r.v1_ratio], [i, i], color=GRID, lw=2, zorder=1)
ax.scatter(df.v1_ratio, y, s=60, color=V1, edgecolors=SURFACE, linewidths=1.5, zorder=3, label="v1: predicts price level")
ax.scatter(df.v2_ratio, y, s=60, color=V2, edgecolors=SURFACE, linewidths=1.5, zorder=3, label="v2: predicts next-day return")
ax.axvline(1, color=INK2, lw=1, ls=(0, (4, 3)), zorder=2)
ax.set_ylim(-1.1, len(df) - 0.5)
ax.text(1.06, -0.85, "← naive forecast (tomorrow = today)", color=INK2, fontsize=8.5, va="center")
for i, (_, r) in enumerate(df.iterrows()):
    ax.text(r.v1_ratio + 0.15, i, f"{r.v1_ratio:.1f}×", va="center", color=INK2, fontsize=8.5)
ax.set_yticks(list(y), df.index)
ax.set_xlim(0.8, 9)
ax.set_xlabel("1-day forecast error ÷ naive forecast error  (lower is better, 1.0 = naive)", color=INK2)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.tick_params(colors=INK2, length=0)
ax.grid(True, axis="x", color=GRID, lw=0.6); ax.set_axisbelow(True)
ax.legend(loc="lower right", frameon=False, fontsize=9)
fig.suptitle("Benchmarking against the naive forecast", x=0.03, ha="left", color=INK, fontsize=12, fontweight="bold")
ax.set_title("Walk-forward CV, 5 folds, Feb 2024 – Mar 2026. The v1 level models were 2–8× worse than naive; v2 is within 2–14 %.",
             loc="left", color=INK2, fontsize=8.5, pad=8)
fig.tight_layout()
fig.savefig(FIG / "model_benchmark.png", facecolor=SURFACE)
print("saved", FIG / "model_benchmark.png")
