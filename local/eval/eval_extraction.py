"""Manual eval for the REAL tablet. NOT run by pytest.

Run ONLY on the tablet, requires the real model + llama binary:
    python -m local.eval.eval_extraction --config config.json \
        --data local/eval/conversations.json

conversations.json: [{"id": "c1", "lang": "hinglish",
                      "user": "...", "assistant": "..."}, ...]   (30-50 items)
Model path: config["local_model"]["model_path"] or env RAVEN_MODEL_PATH.
Report: local/eval/report_<timestamp>.json (contains test conversations
and extracted facts, so use only fake data).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
from pathlib import Path

from local.runner import LocalRunner
from local.extractor import Extractor


class _CollectMemory:
    """Stand-in memory: collects facts, never touches the real DB."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, content, **kw):
        self.items.append({"content": content, **kw})


def _mem_available_mb() -> int:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


class _PeakRam:
    """Samples MemAvailable; peak used = baseline - min seen."""

    def __init__(self) -> None:
        self.base = _mem_available_mb()
        self.min = self.base
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(0.2):
            cur = _mem_available_mb()
            if cur != -1 and (self.min == -1 or cur < self.min):
                self.min = cur

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self._t.join(timeout=1)

    @property
    def peak_used_mb(self) -> int:
        return -1 if self.base == -1 else max(0, self.base - self.min)


def _ask_mark(fact: dict) -> str:
    while True:
        ans = input(f"   [{fact['category']}/s{fact['sensitivity']}] "
                    f"{fact['content']}\n   correct? (y/n/s=skip): ").strip().lower()
        if ans in ("y", "n", "s"):
            return ans


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--data", default="local/eval/conversations.json")
    ap.add_argument("--no-mark", action="store_true", help="skip manual marking")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))["local_model"]
    env_model = os.environ.get("RAVEN_MODEL_PATH")
    if env_model:
        cfg["model_path"] = env_model
    convs = json.loads(Path(args.data).read_text(encoding="utf-8"))

    runner = LocalRunner(cfg)
    runner.load()
    memory = _CollectMemory()
    extractor = Extractor(runner, memory, cfg)

    rows, latencies = [], []
    correct = wrong = 0
    with _PeakRam() as peak:
        for i, c in enumerate(convs, 1):
            before = len(memory.items)
            t0 = time.monotonic()
            facts = extractor.extract(c["user"], c["assistant"])
            dt = time.monotonic() - t0
            latencies.append(dt)
            print(f"\n[{i}/{len(convs)}] {c.get('id')} ({c.get('lang')}) "
                  f"{dt:.1f}s facts={len(facts)}")
            marks = []
            for f in facts:
                m = "s" if args.no_mark else _ask_mark(f)
                marks.append(m)
                correct += m == "y"
                wrong += m == "n"
            rows.append({
                "id": c.get("id"), "lang": c.get("lang"),
                "latency_s": round(dt, 2), "facts": facts, "marks": marks,
                "saved": len(memory.items) - before,
            })
    runner.unload()

    judged = correct + wrong
    report = {
        "turns": len(convs),
        "avg_facts_per_turn": round(sum(len(r["facts"]) for r in rows) / max(1, len(rows)), 2),
        "avg_latency_s": round(statistics.mean(latencies), 2) if latencies else 0,
        "max_latency_s": round(max(latencies), 2) if latencies else 0,
        "peak_ram_used_mb": peak.peak_used_mb,
        "precision": round(correct / judged, 3) if judged else None,
        "results": rows,
    }
    out = Path(__file__).parent / f"report_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport saved: {out.name}")
    print({k: v for k, v in report.items() if k != "results"})


if __name__ == "__main__":
    main()