"""
CLI Batch Runner for UGC NET CS JRF Solver (Multi-Key Edition)
"""

import os
import sys
import argparse
import signal
from solver_core import (
    OUTPUT_FILE_DEFAULT,
    PDF_DIR_DEFAULT,
    run_solver_batch,
    request_stop,
    clear_stop_request,
    GLOBAL_KEY_MANAGER
)


def safe_print(message):
    print(str(message).encode("ascii", errors="backslashreplace").decode("ascii"))


def signal_handler(sig, frame):
    safe_print("\n[!] Ctrl+C detected! Pausing cleanly after current chunk commits...")
    request_stop()

def main():
    parser = argparse.ArgumentParser(description="UGC NET JRF Multi-Key Solver CLI")
    parser.add_argument("--pdf-dir", type=str, default=PDF_DIR_DEFAULT)
    parser.add_argument("--output", type=str, default=OUTPUT_FILE_DEFAULT)
    parser.add_argument("--api-key", type=str, default=None, help="Optional Gemini API key")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash-lite")
    parser.add_argument("--chunk-size", type=int, default=2500)
    parser.add_argument("--delay", type=float, default=5.0)

    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal_handler)
    clear_stop_request()

    if args.api_key:
        GLOBAL_KEY_MANAGER.update_keys([args.api_key], [], [])

    total_keys = GLOBAL_KEY_MANAGER.total_keys()
    if total_keys == 0:
        safe_print("[ERROR] No API keys found! Add your keys to .env or set GEMINI_API_KEYS / GROQ_API_KEYS.")
        sys.exit(1)

    safe_print("=" * 60)
    safe_print("🎓 UGC NET Computer Science JRF AI Engine (Multi-Key Runner)")
    safe_print(f"Active Key Pool:     {total_keys} keys rotating in pool")
    safe_print(f"Primary Model:       {args.model}")
    safe_print(f"Delay Between Calls: {args.delay}s")
    safe_print("=" * 60)
    safe_print("Press Ctrl+C at any time to pause safely.\n")

    def progress_callback(curr, total, msg):
        pct = (curr / max(total, 1)) * 100
        safe_print(f"[{pct:5.1f}%] [{curr}/{total}] {msg}")

    def status_callback(msg):
        safe_print(f"  -> {msg}")

    try:
        run_solver_batch(
            key_manager=GLOBAL_KEY_MANAGER,
            pdf_dir=args.pdf_dir,
            output_file=args.output,
            model=args.model,
            chunk_size=args.chunk_size,
            inter_request_delay=args.delay,
            on_progress=progress_callback,
            status_callback=status_callback
        )
        safe_print("\n[DONE] Execution completed.")
    except KeyboardInterrupt:
        safe_print("\n[PAUSED] Process interrupted. Progress saved.")

if __name__ == "__main__":
    main()
