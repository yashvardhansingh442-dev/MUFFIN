#!/usr/bin/env python3
"""Regenerate the README images in docs/assets/ from the repository itself.

Every number is measured (lines, tests, coverage, latency) or parsed from README.md
(roadmap, OWASP table, limitations), never typed by hand.

    pip install -e ".[dev]" pytest-cov matplotlib
    python scripts/make_readme_assets.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Wedge

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
sys.path.insert(0, str(ROOT / "src"))

BG, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TXT, MUTED = "#e6edf3", "#8b949e"
BLUE, PURPLE, GREEN, ORANGE, AMBER, RED = "#58a6ff", "#bc8cff", "#3fb950", "#f78166", "#d29922", "#f85149"
PALETTE = [BLUE, PURPLE, GREEN, ORANGE, AMBER, "#79c0ff", "#ff7b72", "#56d364", "#d2a8ff"]


# --------------------------------------------------------------------------- stats
def run(*args: str) -> str:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True).stdout


def measure() -> dict:
    s: dict = {}
    s["loc"] = {
        p.stem: sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())
        for p in sorted((ROOT / "src" / "muffin").glob("*.py"))
    }
    collected = run("-m", "pytest", "--collect-only", "-q")
    per_file = Counter(m.group(1) for m in re.finditer(r"^tests/(\w+)\.py::", collected, re.M))
    s["tests"] = dict(per_file)
    s["n_tests"] = sum(per_file.values())

    cov_json = Path(tempfile.mkdtemp()) / "cov.json"
    out = run("-m", "pytest", "-q", "--cov=muffin", f"--cov-report=json:{cov_json}")
    m = re.search(r"in ([\d.]+)s", out)
    s["test_seconds"] = float(m.group(1)) if m else None
    s["passed"] = int(re.search(r"(\d+) passed", out).group(1)) if "passed" in out else 0
    s["failed"] = int(re.search(r"(\d+) failed", out).group(1)) if "failed" in out else 0
    s["cov"], s["cov_total"] = {}, None
    if cov_json.exists():
        data = json.loads(cov_json.read_text())
        s["cov"] = {Path(k).stem: v["summary"]["percent_covered"] for k, v in data["files"].items()}
        s["cov_total"] = data["totals"]["percent_covered"]

    from muffin import Action, Agent, Policy, Runtime, SafetyLayer, rules

    def check_latency(extra_rules: int, n: int) -> np.ndarray:
        pr = {"send": [rules.only_keys("to", "body"), rules.email_domain("to", "example.com"),
                       rules.max_len("body", 200)] + [rules.max_len("body", 200)] * extra_rules}
        layer = SafetyLayer()
        layer.register("a", Policy({"send"}, costs={"send": 1}, param_rules=pr))
        act = Action("send", {"to": "a@example.com", "body": "hi"})
        ts = np.empty(n)
        for i in range(n):
            t = time.perf_counter()
            layer.check("a", act)
            ts[i] = (time.perf_counter() - t) * 1e6
        return ts

    def best(extra_rules: int, n: int) -> np.ndarray:
        # Three runs, keep the quietest: scheduler noise only ever makes timings worse.
        runs = [check_latency(extra_rules, n) for _ in range(3)]
        return min(runs, key=np.median)

    base = best(0, 20000)
    s["lat_samples"] = base
    s["lat"] = {3: base, 8: best(5, 5000), 23: best(20, 5000)}

    class Ping(Agent):
        def decide(self):
            return Action("send", {})

        def act(self, action):
            return "ok"

    rt = Runtime()
    aid = rt.spawn(Ping(), Policy({"send"}, costs={"send": 1}))
    rt.start(aid)
    n = 3000
    timings = []
    for _ in range(3):
        t = time.perf_counter()
        for _ in range(n):
            rt.step(aid)
        timings.append((time.perf_counter() - t) / n * 1e6)
    s["step_us"] = min(timings)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    road = readme[readme.index("## 16. Roadmap"): readme.index("## 17.")]
    s["roadmap"] = []
    for block in re.split(r"^### ", road, flags=re.M)[1:]:
        title = block.splitlines()[0]
        label = re.match(r"Stage (\w)", title)
        s["roadmap"].append((label.group(1) if label else title[:1],
                             re.sub(r"^Stage \w: ", "", title).replace("*(in progress)*", "").strip(),
                             block.count("- [x]"), block.count("- [ ]")))

    own = readme[readme.index("### 7.3"): readme.index("### 7.4")]
    s["owasp"] = []
    for row in re.findall(r"^\| (ASI\d+) ([^|]+)\| ([^|]+)\|", own, re.M):
        status = re.sub(r"[*`]", "", row[2]).strip().split()[0].lower()
        s["owasp"].append((row[0], row[1].strip(), {"partial": "Partial", "none": "None"}.get(status, "N/A")))

    lim = readme[readme.index("## 15."): readme.index("## 16.")]
    sev = Counter()
    for row in re.findall(r"^\| (L\d+) \|.*?\| ([^|]+) \|[^|]*\|$", lim, re.M):
        m = re.match(r"(Low-Medium|Low|Medium|High|Fixed|n/a)", row[1].strip())
        sev[m.group(1) if m else "Other"] += 1
    s["limits"] = sev
    s["medium_titles"] = []
    for row in re.findall(r"^\| (L\d+) \| (.*?) \| Medium[^|]*\| [^|]*\|$", lim, re.M):
        m = re.search(r"\*\*(.+?)\*\*", row[1])
        if m:
            s["medium_titles"].append((row[0], m.group(1).rstrip(".")))
    return s


# --------------------------------------------------------------------------- drawing helpers
def canvas(w: int, h: int, bg: str = BG):
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100, facecolor=bg)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, fc=CARD, ec=BORDER, r=14, lw=1.6, z=2, alpha=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, zorder=z, alpha=alpha))


def text(ax, x, y, s, size=16, color=TXT, weight="normal", ha="left", va="center", z=5, **kw):
    ax.text(x, y, s, fontsize=size, color=color, fontweight=weight, ha=ha, va=va, zorder=z, **kw)


def arrow(ax, p, q, color=MUTED, lw=2.4, style="-|>", rad=0.0, z=4):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=18, color=color, lw=lw,
                                 connectionstyle=f"arc3,rad={rad}", zorder=z))


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("wrote", OUT / name)


def style_axes(ax, title: str = ""):
    ax.set_facecolor(CARD)
    for sp in ax.spines.values():
        sp.set_color(BORDER)
    ax.tick_params(colors=MUTED, labelsize=13)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    if title:
        ax.set_title(title, color=TXT, fontsize=18, fontweight="bold", loc="left", pad=14)


def cupcake(ax, cx, cy, k=1.0):
    ax.add_patch(Polygon([(cx - 52 * k, cy + 6 * k), (cx + 52 * k, cy + 6 * k),
                          (cx + 38 * k, cy + 72 * k), (cx - 38 * k, cy + 72 * k)], fc="#a371f7", ec="none", zorder=5))
    for dx in (-26, -9, 9, 26):
        ax.plot([cx + dx * k, cx + dx * 0.78 * k], [cy + 10 * k, cy + 70 * k], color="#6e40c9", lw=3 * k, zorder=6)
    ax.add_patch(Wedge((cx, cy + 8 * k), 60 * k, 180, 360, fc="#f0b8d0", ec="none", zorder=6))
    ax.add_patch(Wedge((cx, cy - 20 * k), 34 * k, 180, 360, fc="#ffd6e7", ec="none", zorder=6))
    ax.add_patch(Circle((cx, cy - 58 * k), 10 * k, fc=RED, ec="none", zorder=7))


# --------------------------------------------------------------------------- images
def banner(S):
    W, H = 1600, 430
    fig, ax = canvas(W, H)
    cmap = LinearSegmentedColormap.from_list("b", ["#0d1117", "#1c1445", "#0b2a4a"])
    ax.imshow(np.linspace(0, 1, 256).reshape(1, -1), extent=[0, W, H, 0], cmap=cmap, aspect="auto", zorder=0)
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    cupcake(ax, 120, 150, 1.25)
    text(ax, 235, 105, "MUFFIN.AI", 70, TXT, "bold")
    text(ax, 238, 178, "A safety-and-memory runtime for AI agents", 27, "#c9d1d9")
    text(ax, 238, 232, "The agent proposes.  MUFFIN decides, remembers, and records.", 20, BLUE)

    chips = [("0", "runtime deps"), (f"{S['n_tests']}", "tests"),
             (f"{S['cov_total']:.0f}%" if S["cov_total"] else "n/a", "coverage"),
             (f"~{np.median(S['lat_samples']):.0f} \u00b5s", "per safety check")]
    x = 60
    for big, small in chips:
        box(ax, x, 300, 340, 92, fc="#161b22", ec="#30363d", r=18, alpha=0.9)
        text(ax, x + 28, 336, big, 34, GREEN, "bold")
        text(ax, x + 28, 372, small, 17, MUTED)
        x += 375

    # mini pipeline on the right
    nodes = [("AI agent", 985, BLUE), ("MUFFIN", 1210, PURPLE), ("Real world", 1450, GREEN)]
    for label, nx, col in nodes:
        box(ax, nx - 85, 70, 170, 70, fc="#0d1117", ec=col, r=16, lw=2.4)
        text(ax, nx, 105, label, 18, col, "bold", "center")
    arrow(ax, (1074, 105), (1120, 105), TXT)
    arrow(ax, (1298, 105), (1360, 105), GREEN)
    text(ax, 1329, 124, "allowed", 12, GREEN, "bold", "center")
    arrow(ax, (1210, 142), (1210, 168), RED)
    box(ax, 1100, 170, 220, 34, fc="#2d1214", ec=RED, r=12)
    text(ax, 1210, 187, "blocked + logged", 13, RED, "bold", "center")
    save(fig, "banner.png")


def flow(S):
    W, H = 1600, 650
    fig, ax = canvas(W, H)
    text(ax, 40, 38, "How one step works", 30, TXT, "bold")
    text(ax, 40, 74, "Model proposes, runtime disposes: the agent never executes anything directly.", 17, MUTED)

    box(ax, 40, 250, 230, 120, ec=BLUE, lw=2.4)
    text(ax, 155, 292, "AI agent", 26, BLUE, "bold", "center")
    text(ax, 155, 333, "perceive \u00b7 decide", 16, MUTED, ha="center")
    arrow(ax, (272, 310), (324, 310), TXT)
    box(ax, 326, 280, 244, 60, fc="#0d1117", ec=MUTED, r=30)
    text(ax, 448, 302, "proposed Action", 16, TXT, "bold", "center")
    text(ax, 448, 324, "send_email(to=...)", 13, MUTED, ha="center")
    arrow(ax, (572, 310), (618, 310), TXT)

    box(ax, 620, 100, 470, 520, fc="#1a1330", ec=PURPLE, lw=2.4, r=22)
    text(ax, 855, 135, "MUFFIN safety layer", 25, PURPLE, "bold", "center")
    checks = ["Kill switch off?", "Policy registered?", "Action well-formed (cost)?", "On the allowlist?",
              "Within lifetime budget?", "Under the rate limit?", "Argument rules pass?", "Custom constraints pass?"]
    for i, c in enumerate(checks):
        y = 165 + i * 55
        box(ax, 650, y, 410, 44, fc="#241a42", ec="#4c3a85", r=10, lw=1.2)
        text(ax, 676, y + 22, str(i + 1), 17, PURPLE, "bold")
        text(ax, 712, y + 22, c, 17, TXT)

    arrow(ax, (1092, 250), (1190, 190), GREEN, rad=-0.1)
    text(ax, 1130, 238, "all pass", 15, GREEN, "bold", "center")
    box(ax, 1190, 130, 370, 100, ec=GREEN, lw=2.2)
    text(ax, 1375, 166, "Execute the action", 22, GREEN, "bold", "center")
    text(ax, 1375, 203, "then charge the budget", 15, MUTED, ha="center")
    arrow(ax, (1375, 232), (1375, 290), GREEN)
    box(ax, 1190, 292, 370, 100, ec=BLUE, lw=2.2)
    text(ax, 1375, 328, "Record it", 22, BLUE, "bold", "center")
    text(ax, 1375, 365, "memory + decision trace", 15, MUTED, ha="center")

    arrow(ax, (1092, 470), (1190, 500), RED, rad=0.1)
    text(ax, 1130, 535, "any fails", 15, RED, "bold", "center")
    box(ax, 1190, 450, 370, 120, fc="#2d1214", ec=RED, lw=2.2)
    text(ax, 1375, 490, "Blocked", 24, RED, "bold", "center")
    text(ax, 1375, 530, "reason saved to memory and trace", 14, MUTED, ha="center")
    text(ax, 1375, 552, "(nothing was executed)", 13, MUTED, ha="center")
    save(fig, "flow.png")


def kpis(S):
    W, H = 1600, 600
    fig, ax = canvas(W, H)
    cov = S["cov"]
    weakest = min(cov, key=cov.get) if cov else None
    done = sum(r[2] for r in S["roadmap"])
    total = sum(r[2] + r[3] for r in S["roadmap"])
    a = S["roadmap"][0]
    cards = [
        (f"{sum(S['loc'].values()):,}", "lines of code", f"{len(S['loc'])} modules \u00b7 standard library only", BLUE),
        (f"{S['n_tests']}", "test cases", f"{len(S['tests'])} files \u00b7 " + (f"{S['test_seconds']:.1f}s to run" if S["test_seconds"] else ""), GREEN),
        (f"{S['cov_total']:.0f}%" if S["cov_total"] else "n/a", "line coverage", f"weakest: {weakest} {cov[weakest]:.0f}%" if weakest else "", AMBER),
        (f"{np.median(S['lat_samples']):.0f} \u00b5s", "median safety check", f"p99 {np.percentile(S['lat_samples'], 99):.0f} \u00b5s \u00b7 full step ~{S['step_us']:.0f} \u00b5s", PURPLE),
        ("0", "runtime dependencies", "install it and go", GREEN),
        (f"{done}/{total}", "roadmap milestones", f"Stage {a[0]}: {a[2]} of {a[2] + a[3]} done", ORANGE),
    ]
    cw, ch, gap = 486, 250, 30
    for i, (big, label, sub, col) in enumerate(cards):
        x = 40 + (i % 3) * (cw + gap)
        y = 40 + (i // 3) * (ch + gap)
        box(ax, x, y, cw, ch, r=22)
        ax.add_patch(FancyBboxPatch((x, y + 30), 8, ch - 60, boxstyle="round,pad=0,rounding_size=4", fc=col, ec="none", zorder=3))
        text(ax, x + 44, y + 92, big, 66, col, "bold")
        text(ax, x + 46, y + 160, label, 23, TXT, "bold")
        text(ax, x + 46, y + 200, sub, 16, MUTED)
    save(fig, "kpis.png")


def code_map(S):
    W, H = 1600, 560
    fig, ax = canvas(W, H)
    loc = dict(sorted(S["loc"].items(), key=lambda kv: -kv[1]))
    roles = {"runtime": "lifecycle, step loop, rollback", "safety": "default-deny enforcement",
             "memory": "SQLite episodic event log", "llm_agent": "LLM as the decide step",
             "trace": "append-only decision trace", "rules": "argument checks, fail closed",
             "agent": "Agent and Action base types", "providers": "model provider (Anthropic)",
             "__init__": "public API exports"}
    total = sum(loc.values())
    text(ax, 40, 44, "Where the code lives", 30, TXT, "bold")
    text(ax, 40, 80, f"{total:,} non-blank lines in src/muffin, standard library only", 17, MUTED)
    cx, cy, R = 330, 320, 190
    ang = 90.0
    for i, (name, n) in enumerate(loc.items()):
        sweep = n / total * 360
        ax.add_patch(Wedge((cx, cy), R, -(ang + sweep), -ang, width=70, fc=PALETTE[i % len(PALETTE)], ec=BG, lw=3, zorder=3))
        ang += sweep
    text(ax, cx, cy - 12, f"{total:,}", 46, TXT, "bold", "center")
    text(ax, cx, cy + 32, "lines", 20, MUTED, ha="center")
    y = 135
    maxn = max(loc.values())
    for i, (name, n) in enumerate(loc.items()):
        col = PALETTE[i % len(PALETTE)]
        ax.add_patch(Circle((660, y), 9, fc=col, ec="none", zorder=4))
        text(ax, 690, y, f"{name}.py", 20, TXT, "bold")
        text(ax, 920, y, roles.get(name, ""), 15, MUTED)
        bw = n / maxn * 200
        ax.add_patch(FancyBboxPatch((1250, y - 9), bw, 18, boxstyle="round,pad=0,rounding_size=6", fc=col, ec="none", zorder=4, alpha=0.9))
        text(ax, 1250 + bw + 12, y, str(n), 16, TXT)
        y += 46
    save(fig, "code_map.png")


def quality(S):
    fig = plt.figure(figsize=(16, 6.2), dpi=100, facecolor=BG)
    fig.text(0.025, 0.94, "Tests and coverage", color=TXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.025, 0.875, f"{S['n_tests']} test cases, {S['passed']} passing locally"
             + (f", {S['cov_total']:.0f}% of lines covered" if S["cov_total"] else ""), color=MUTED, fontsize=17, va="center")

    ax1 = fig.add_axes([0.13, 0.12, 0.33, 0.62])
    names = sorted(S["tests"], key=S["tests"].get)
    ax1.barh([n.replace("test_", "") for n in names], [S["tests"][n] for n in names], color=BLUE, height=0.62)
    style_axes(ax1, "Test cases per file")
    for i, n in enumerate(names):
        ax1.text(S["tests"][n] + 0.8, i, str(S["tests"][n]), color=TXT, va="center", fontsize=14, fontweight="bold")
    ax1.set_xlim(0, max(S["tests"].values()) * 1.18)
    ax1.grid(axis="x", color=BORDER, alpha=0.5)
    ax1.set_axisbelow(True)

    ax2 = fig.add_axes([0.60, 0.12, 0.37, 0.62])
    cov = dict(sorted(S["cov"].items(), key=lambda kv: kv[1], reverse=True))
    labels = list(cov)[::-1]
    vals = [cov[k] for k in labels]
    cols = [GREEN if v >= 90 else AMBER if v >= 80 else ORANGE if v >= 60 else RED for v in vals]
    ax2.barh(labels, vals, color=cols, height=0.62)
    style_axes(ax2, "Line coverage per module")
    for i, v in enumerate(vals):
        ax2.text(v + 1.2, i, f"{v:.0f}%", color=TXT, va="center", fontsize=14, fontweight="bold")
    if S["cov_total"]:
        ax2.axvline(S["cov_total"], color=PURPLE, ls="--", lw=2)
        ax2.text(S["cov_total"] - 1, len(labels) - 0.35, f"overall {S['cov_total']:.0f}%", color=PURPLE, ha="right", fontsize=13, fontweight="bold")
    ax2.set_xlim(0, 112)
    ax2.grid(axis="x", color=BORDER, alpha=0.5)
    ax2.set_axisbelow(True)
    save(fig, "quality.png")


def owasp(S):
    W, H = 1600, 580
    fig, ax = canvas(W, H)
    cnt = Counter(s for _, _, s in S["owasp"])
    text(ax, 40, 44, "Coverage of the OWASP Top 10 for Agentic Applications (2026)", 30, TXT, "bold")
    text(ax, 40, 80, f"Self-assessed for v0.1: {cnt['Partial']} partial, {cnt['None']} not yet covered, {cnt['N/A']} not applicable yet. A map of the work ahead, not a score.", 17, MUTED)
    colors = {"Partial": (AMBER, "#2a2110"), "None": (RED, "#2d1214"), "N/A": (MUTED, "#1c2128")}
    tw, th, gap = 290, 200, 22
    for i, (aid, name, st) in enumerate(S["owasp"]):
        x = 40 + (i % 5) * (tw + gap)
        y = 120 + (i // 5) * (th + gap)
        edge, fill = colors[st]
        box(ax, x, y, tw, th, fc=fill, ec=edge, r=18, lw=2.2)
        text(ax, x + 22, y + 36, aid, 24, edge, "bold")
        ax.text(x + 22, y + 92, name, fontsize=18, color=TXT, fontweight="bold", va="center", zorder=5, wrap=True)
        label = {"Partial": "PARTIAL", "None": "NOT YET", "N/A": "N/A YET"}[st]
        box(ax, x + 22, y + th - 56, 120, 34, fc=edge, ec="none", r=17)
        text(ax, x + 82, y + th - 39, label, 14, BG, "bold", "center")
    save(fig, "owasp.png")


def roadmap(S):
    W, H = 1600, 520
    fig, ax = canvas(W, H)
    done = sum(r[2] for r in S["roadmap"])
    total = sum(r[2] + r[3] for r in S["roadmap"])
    text(ax, 40, 44, "Roadmap progress", 30, TXT, "bold")
    text(ax, 40, 80, "A milestone counts as done only when its acceptance criteria are met.", 17, MUTED)
    box(ax, 1180, 110, 380, 360, r=22)
    text(ax, 1370, 235, f"{done / total * 100:.0f}%", 84, ORANGE, "bold", "center")
    text(ax, 1370, 315, f"{done} of {total} milestones", 22, TXT, "bold", "center")
    text(ax, 1370, 352, "all stages combined", 16, MUTED, ha="center")
    y = 125
    for stage, name, d, o in S["roadmap"]:
        n = d + o
        text(ax, 40, y + 22, f"Stage {stage}", 20, TXT, "bold")
        text(ax, 40, y + 50, name[:44], 14, MUTED)
        bx, bw = 430, 620
        box(ax, bx, y + 4, bw, 40, fc="#21262d", ec="none", r=20)
        if d:
            box(ax, bx, y + 4, max(bw * d / n, 40), 40, fc=GREEN, ec="none", r=20)
        text(ax, bx + bw + 20, y + 25, f"{d}/{n}", 19, TXT, "bold")
        y += 76
    save(fig, "roadmap.png")


def latency(S):
    fig = plt.figure(figsize=(16, 6), dpi=100, facecolor=BG)
    fig.text(0.025, 0.94, "Speed: what does mediation cost?", color=TXT, fontsize=30, fontweight="bold", va="center")
    fig.text(0.025, 0.875, "Measured on one machine (Python 3.12, in-memory storage). Read it as an order of magnitude, not a benchmark.", color=MUTED, fontsize=16, va="center")
    ax1 = fig.add_axes([0.07, 0.13, 0.42, 0.62])
    samples = S["lat_samples"]
    hi = np.percentile(samples, 99.5)
    ax1.hist(samples[samples <= hi], bins=70, color=PURPLE, alpha=0.95)
    style_axes(ax1, f"Safety check, {len(samples):,} calls (3 rules)")
    p50, p99 = np.median(samples), np.percentile(samples, 99)
    ax1.axvline(p50, color=GREEN, lw=2.5)
    ax1.axvline(p99, color=ORANGE, lw=2.5, ls="--")
    ax1.text(p50, ax1.get_ylim()[1] * 0.45, f" median {p50:.1f} \u00b5s", color=GREEN, fontsize=15, fontweight="bold")
    ax1.text(min(p99, hi * 0.98), ax1.get_ylim()[1] * 0.18, f" p99 {p99:.0f} \u00b5s", color=ORANGE, fontsize=15, fontweight="bold")
    ax1.set_yscale("log")
    ax1.set_xlabel("microseconds per check", fontsize=14)
    ax1.set_ylabel("calls (log scale)", fontsize=14)

    ax2 = fig.add_axes([0.58, 0.13, 0.39, 0.62])
    labels = [f"check, {k} rules" for k in S["lat"]] + ["full step\n(check+act+record)"]
    vals = [float(np.median(v)) for v in S["lat"].values()] + [S["step_us"]]
    ax2.barh(labels[::-1], vals[::-1], color=[ORANGE, PURPLE, PURPLE, PURPLE], height=0.6)
    style_axes(ax2, "Median cost (\u00b5s, lower is better)")
    for i, v in enumerate(vals[::-1]):
        ax2.text(v + 2, i, f"{v:.0f} \u00b5s" if v >= 20 else f"{v:.1f} \u00b5s", color=TXT, va="center", fontsize=15, fontweight="bold")
    ax2.set_xlim(0, max(vals) * 1.25)
    ax2.grid(axis="x", color=BORDER, alpha=0.5)
    ax2.set_axisbelow(True)
    save(fig, "latency.png")


def limits(S):
    W, H = 1600, 460
    fig, ax = canvas(W, H)
    order = [("Medium", AMBER), ("Low-Medium", "#e3b341"), ("Low", BLUE), ("Fixed", GREEN), ("n/a", MUTED)]
    total = sum(S["limits"].values())
    text(ax, 40, 44, f"{total} documented limitations", 30, TXT, "bold")
    text(ax, 40, 80, "Listed so nobody relies on a guarantee that is not there. Each one has a severity and a workaround in the README.", 17, MUTED)
    x = 40
    for name, col in order:
        n = S["limits"].get(name, 0)
        if not n:
            continue
        w = (W - 80) * n / total
        box(ax, x, 130, w - 8, 130, fc=col, ec="none", r=18, alpha=0.92)
        text(ax, x + (w - 8) / 2, 180, str(n), 54, BG, "bold", "center")
        text(ax, x + (w - 8) / 2, 232, name.replace("Low-Medium", "Low-Med"), 18 if w > 160 else 12, BG, "bold", "center")
        x += w
    text(ax, 40, 315, f"The {len(S['medium_titles'])} Medium items:", 18, AMBER, "bold")
    for i, (lid, title) in enumerate(S["medium_titles"][:6]):
        col, row = divmod(i, 3)
        clean = title.replace("`", "")
        clean = clean if len(clean) <= 56 else clean[:55].rstrip() + "..."
        text(ax, 40 + col * 780, 352 + row * 30, f"{lid}  {clean}", 15, TXT)
    save(fig, "limitations.png")


def main() -> None:
    S = measure()
    for fn in (banner, flow, kpis, code_map, quality, owasp, roadmap, latency, limits):
        fn(S)
    summary = {"loc": sum(S["loc"].values()), "tests": S["n_tests"], "coverage": S["cov_total"],
               "check_p50_us": float(np.median(S["lat_samples"])), "step_us": S["step_us"]}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
