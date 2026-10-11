"""Phase 3 preview: show the exact outgoing payload, ask Send/Cancel.

Any input problem (EOF, Ctrl-C) counts as NO (cancel).
"""
from __future__ import annotations

import json


def _ask(prompt: str) -> bool:
    while True:
        try:
            ans = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if ans in {"y", "yes", "s", "send"}:
            return True
        if ans in {"n", "no", "c", "cancel"}:
            return False
        print("Please answer y or n.")


def ask_permission(reason: str) -> bool:
    """Sensitive topic: ask before continuing (masking still applies)."""
    print(f"\n[!] Sensitive topic detected ({reason}).")
    print("    Personal data is still masked before sending.")
    return _ask("Continue? (y/n): ")


def confirm_send(payload: dict, models: list) -> bool:
    """Show EXACTLY what will leave the device; True = Send, False = Cancel."""
    print("\n===== WILL BE SENT TO CLOUD =====")
    print("Models (in order):", ", ".join(models) if models else "(none)")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("=================================")
    return _ask("Send? (y = send / n = cancel): ")