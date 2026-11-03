"""
Multi-Provider & Multi-Key Failover Manager for UGC NET JRF Solver
Supports:
- Google Gemini (API key rotation across multiple accounts)
- Groq (DeepSeek-R1-Distill-Llama-70B, Llama-3.3-70B)
- OpenRouter (DeepSeek R1, Qwen 2.5 72B, etc.)
- Automatic cooldown tracking, round-robin, and cross-provider failover
"""

import os
import time
import json
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load .env file automatically
load_dotenv()

class APIKeyPool:
    def __init__(self):
        self.keys: Dict[str, List[Dict[str, Any]]] = {
            "gemini": [],
            "groq": [],
            "openrouter": []
        }
        self.indices: Dict[str, int] = {"gemini": 0, "groq": 0, "openrouter": 0}
        self.load_from_environment()

    def load_from_environment(self):
        """Loads keys from .env or OS environment variables."""
        # Gemini keys
        gemini_raw = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
        self.set_keys("gemini", self._parse_keys_str(gemini_raw))

        # Groq keys
        groq_raw = os.environ.get("GROQ_API_KEYS", "") or os.environ.get("GROQ_API_KEY", "")
        self.set_keys("groq", self._parse_keys_str(groq_raw))

        # OpenRouter keys
        or_raw = os.environ.get("OPENROUTER_API_KEYS", "") or os.environ.get("OPENROUTER_API_KEY", "")
        self.set_keys("openrouter", self._parse_keys_str(or_raw))

    def _parse_keys_str(self, raw: str) -> List[str]:
        if not raw:
            return []
        # Support comma, semicolon, newline, or space separation
        items = [k.strip() for k in raw.replace(";", ",").replace("\n", ",").split(",") if k.strip()]
        return list(dict.fromkeys(items))  # preserve order & unique

    def set_keys(self, provider: str, key_list: List[str]):
        """Sets keys for a specific provider."""
        existing_map = {k["key"]: k for k in self.keys.get(provider, [])}
        new_pool = []
        for key in key_list:
            if not key:
                continue
            if key in existing_map:
                new_pool.append(existing_map[key])
            else:
                new_pool.append({
                    "key": key,
                    "cooldown_until": 0.0,
                    "errors": 0,
                    "successes": 0
                })
        self.keys[provider] = new_pool

    def get_keys(self, provider: str) -> List[str]:
        return [k["key"] for k in self.keys.get(provider, [])]

    def has_any_keys(self) -> bool:
        return any(len(self.keys[p]) > 0 for p in self.keys)

    def mark_rate_limited(self, provider: str, key: str, cooldown_seconds: float = 60.0):
        """Places a key on temporary cooldown after 429 quota exhaustion."""
        for item in self.keys.get(provider, []):
            if item["key"] == key:
                item["cooldown_until"] = time.time() + cooldown_seconds
                item["errors"] += 1
                break

    def mark_success(self, provider: str, key: str):
        """Records a successful API call."""
        for item in self.keys.get(provider, []):
            if item["key"] == key:
                item["successes"] += 1
                item["cooldown_until"] = 0.0
                break

    def get_next_key(self, provider: str) -> Optional[str]:
        """Returns the next available non-cooldown key for a provider."""
        pool = self.keys.get(provider, [])
        if not pool:
            return None
        
        now = time.time()
        start_idx = self.indices[provider] % len(pool)
        
        for offset in range(len(pool)):
            idx = (start_idx + offset) % len(pool)
            candidate = pool[idx]
            if candidate["cooldown_until"] <= now:
                self.indices[provider] = (idx + 1) % len(pool)
                return candidate["key"]
                
        # All keys in cooldown; return key whose cooldown expires earliest
        earliest = min(pool, key=lambda x: x["cooldown_until"])
        return earliest["key"]

    def get_status_summary(self) -> List[Dict[str, Any]]:
        """Returns visual status of all configured keys."""
        summary = []
        now = time.time()
        for provider, pool in self.keys.items():
            for idx, item in enumerate(pool):
                key = item["key"]
                preview = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***"
                is_cooldown = item["cooldown_until"] > now
                remaining = max(0, int(item["cooldown_until"] - now))
                summary.append({
                    "Provider": provider.upper(),
                    "Key #": idx + 1,
                    "Key Preview": preview,
                    "Status": f"⏳ Cooldown ({remaining}s)" if is_cooldown else "🟢 Active & Ready",
                    "Successes": item["successes"],
                    "Errors": item["errors"]
                })
        return summary

# Global pool singleton
key_pool = APIKeyPool()

