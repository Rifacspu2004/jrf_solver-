"""
API Key Verification & Health Diagnostic Script
Tests each key in .env with a minimal prompt to verify connectivity, quota, and authentication.
Masks keys for security.
"""

import os
import sys
import time

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from dotenv import load_dotenv

# Force reload of .env
load_dotenv(override=True)

from solver_core import MultiKeyManager, call_gemini, call_groq, call_openrouter

def test_all_keys():
    km = MultiKeyManager()
    km.load_from_env()

    print("=" * 65)
    print("[DIAGNOSTIC] UGC NET JRF SOLVER - API KEY TEST")
    print("=" * 65)
    print(f"Total keys detected in .env: {km.total_keys()}\n")

    if km.total_keys() == 0:
        print("[!] No keys detected in .env. Please check that .env has your keys defined.")
        return

    results = []
    test_prompt = 'Extract: Q1. In binary tree, max nodes at level L is? Options: 1) 2^L 2) 2^(L-1). Answer in JSON: [{"question": "...", "correct_option": "..."}]'

    for idx, kh in enumerate(km.keys):
        key_num = idx + 1
        provider = kh.provider
        key = kh.key
        preview = kh.preview

        print(f"Testing [{provider.upper()} #{key_num}] Key: {preview} ...", end=" ", flush=True)

        start_time = time.time()
        try:
            if provider == "gemini":
                res = call_gemini(key, test_prompt, model="gemini-3.5-flash-lite")
            elif provider == "groq":
                res = call_groq(key, test_prompt, model="qwen/qwen3.8-27b")
            elif provider == "openrouter":
                res = call_openrouter(key, test_prompt, model="deepseek/deepseek-r1")
            else:
                raise ValueError(f"Unknown provider: {provider}")

            elapsed = time.time() - start_time
            print(f"[PASS] ({elapsed:.2f}s)")
            results.append((provider, preview, "PASS", f"{elapsed:.2f}s"))

        except Exception as e:
            err_msg = str(e).strip()
            print(f"[FAIL]: {err_msg[:80]}")
            results.append((provider, preview, "FAIL", err_msg))

    print("\n" + "=" * 65)
    print("SUMMARY RESULTS")
    print("=" * 65)
    for p, prev, status, note in results:
        sym = "[OK] " if status == "PASS" else "[ERR]"
        print(f"{sym} {p.upper():<11} {prev:<15} : {status:<6} ({note})")
    print("=" * 65)

if __name__ == "__main__":
    test_all_keys()
