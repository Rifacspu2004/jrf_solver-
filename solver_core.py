"""
UGC NET Computer Science (Subject Code 87) JRF PYQ AI Solver Core Engine
Multi-Key & Multi-Provider Failover Architecture (Supports 5-10+ Keys)

Providers:
- Google Gemini (Gemini 2.5 Flash, 2.5 Pro, 1.5 Flash) with key-pool rotation
- Groq (DeepSeek-R1-Distill-Llama-70B, Llama-3.3-70B-Versatile)
- OpenRouter (DeepSeek R1, Qwen 2.5 72B)

Features:
- 5-10 Key Pool: Automatically rotates to next active key upon 429 Rate Limit
- Persistent chunk-level checkpointing in solved_jrf_output.json
- Immediate graceful pause / resume anytime
- Question deduplication & pedagogical student explanation generation
"""

import os
import time
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple
from pypdf import PdfReader
from dotenv import load_dotenv

try:
    import pymupdf
except ImportError:
    pymupdf = None

# Load .env file
load_dotenv()

# Google Gemini SDK
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

# Groq SDK
try:
    from groq import Groq
except ImportError:
    Groq = None

# HTTP client for universal OpenRouter / REST fallback
import httpx

OUTPUT_FILE_DEFAULT = "solved_jrf_output.json"
PDF_DIR_DEFAULT = "pyq_sources"
STOP_SIGNAL_FILE = ".stop_requested"
QUESTION_START_RE = re.compile(
    r"(?m)^[ \t]*(?:(?i:question|q)\s*)?\d{1,2}[.)]"
    r"(?:[ \t]+|[ \t]*\n[ \t]*)(?=[\"'“‘]?[A-Z])"
)

UGC_NET_UNITS = [
    "Unit 1: Discrete Structures & Optimization",
    "Unit 2: Computer System Architecture",
    "Unit 3: Programming Languages & Computer Graphics",
    "Unit 4: Database Management Systems",
    "Unit 5: System Software & Operating System",
    "Unit 6: Software Engineering",
    "Unit 7: Data Structures & Algorithms",
    "Unit 8: Theory of Computation & Compilers",
    "Unit 9: Data Communication & Computer Networks",
    "Unit 10: Artificial Intelligence",
    "General / Research Methodology"
]

EXTRACTION_SYSTEM_PROMPT = r"""You are a Senior Professor, Principal Examiner, and National Top Ranker in UGC NET Computer Science & Applications (Subject Code 87) and GATE Computer Science.

Your mission is to parse UGC NET JRF examination papers from the provided raw text chunk and generate careful, pedagogical solutions for university students and aspirants.

For EVERY question found in the text chunk, extract:
1. "question_number": Question number or ID as stated in paper (e.g. 1, 42, "Q15"). If unknown, assign a sequential index.
2. "question_text": The complete, unabridged question statement. Preserve mathematical formulas, code blocks, or logic expressions using clean LaTeX syntax (e.g., $O(n \log n)$, $\sum$, $\rightarrow$).
3. "options": Key-value dictionary of all available options (e.g. {"1": "...", "2": "...", "3": "...", "4": "..."} or {"A": "...", "B": "...", "C": "...", "D": "..."}).
4. "correct_option": Exact correct option identifier and text (e.g. "Option 2" or "2" or "(B)").
5. "unit_topic": The specific UGC NET CS syllabus unit and specific subtopic (e.g. "Unit 8: Theory of Computation - Decidability & Halting Problem", "Unit 5: Operating Systems - Banker's Algorithm").
6. "explanation": Clear, accurate, step-by-step pedagogical explanation that teaches students the core concept. Include:
   - Fundamental theory, definitions, or axioms.
   - Step-by-step mathematical derivation, truth tables, or trace diagrams where applicable.
   - Do not claim an answer is from an official key unless that key is present in the input.
7. "distractor_analysis": Explain why each provided incorrect option is wrong.
8. "formula_or_exam_tip": A useful formula or exam tip. Do not claim an external reference unless it is present in the input.

Keep each explanation concise but sufficient to justify the answer. Preserve the question wording, options, symbols, and numbering exactly. Do not invent missing questions or answers. Output must be a valid JSON array of objects conforming to this schema. If the chunk contains no complete question, return an empty JSON array []. Do not output Markdown code fences.
"""

# =====================================================================
# MULTI-KEY & MULTI-PROVIDER POOL MANAGER
# =====================================================================

class KeyHealth:
    def __init__(self, key: str, provider: str):
        self.key = key.strip()
        self.provider = provider
        self.cooldown_until: float = 0.0
        self.success_count: int = 0
        self.error_count: int = 0

    @property
    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    @property
    def preview(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return f"{self.key[:4]}...{self.key[-4:]}"

class MultiKeyManager:
    """
    Manages 5-10+ API keys across Gemini, Groq, and OpenRouter.
    Seamlessly rotates and fails over whenever a key hits its quota limit.
    """
    def __init__(self):
        self.keys: List[KeyHealth] = []
        self.current_idx: int = 0
        self.load_from_env()

    def load_from_env(self):
        """Loads keys from .env or system environment."""
        self.keys.clear()
        
        # 1. Load Gemini keys (supports comma-separated GEMINI_API_KEYS or numbered GEMINI_API_KEY_1..10)
        gem_tokens = []
        gem_raw = os.environ.get("GEMINI_API_KEYS", "") or os.environ.get("GEMINI_API_KEY", "")
        gem_tokens.extend(self._split_keys(gem_raw))
        for i in range(1, 21):
            k = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
            if k and k not in gem_tokens:
                gem_tokens.append(k)
        for k in gem_tokens:
            self.keys.append(KeyHealth(k, "gemini"))

        # 2. Load Groq keys (supports comma-separated GROQ_API_KEYS or numbered GROQ_API_KEY_1..10)
        groq_tokens = []
        groq_raw = os.environ.get("GROQ_API_KEYS", "") or os.environ.get("GROQ_API_KEY", "")
        groq_tokens.extend(self._split_keys(groq_raw))
        for i in range(1, 21):
            k = os.environ.get(f"GROQ_API_KEY_{i}", "").strip()
            if k and k not in groq_tokens:
                groq_tokens.append(k)
        for k in groq_tokens:
            self.keys.append(KeyHealth(k, "groq"))

        # 3. Load OpenRouter keys
        or_tokens = []
        or_raw = os.environ.get("OPENROUTER_API_KEYS", "") or os.environ.get("OPENROUTER_API_KEY", "")
        or_tokens.extend(self._split_keys(or_raw))
        for i in range(1, 21):
            k = os.environ.get(f"OPENROUTER_API_KEY_{i}", "").strip()
            if k and k not in or_tokens:
                or_tokens.append(k)
        for k in or_tokens:
            self.keys.append(KeyHealth(k, "openrouter"))

    def _split_keys(self, raw: str) -> List[str]:
        if not raw:
            return []
        tokens = [k.strip() for k in raw.replace(";", ",").replace("\n", ",").split(",") if k.strip()]
        return list(dict.fromkeys(tokens))

    def update_keys(self, gemini_keys: List[str], groq_keys: List[str], openrouter_keys: List[str]):
        """Updates key list dynamically from UI."""
        old_stats = {kh.key: (kh.success_count, kh.error_count) for kh in self.keys}
        self.keys.clear()
        for k in gemini_keys:
            if k.strip():
                kh = KeyHealth(k.strip(), "gemini")
                if kh.key in old_stats:
                    kh.success_count, kh.error_count = old_stats[kh.key]
                self.keys.append(kh)
        for k in groq_keys:
            if k.strip():
                kh = KeyHealth(k.strip(), "groq")
                if kh.key in old_stats:
                    kh.success_count, kh.error_count = old_stats[kh.key]
                self.keys.append(kh)
        for k in openrouter_keys:
            if k.strip():
                kh = KeyHealth(k.strip(), "openrouter")
                if kh.key in old_stats:
                    kh.success_count, kh.error_count = old_stats[kh.key]
                self.keys.append(kh)

    def total_keys(self) -> int:
        return len(self.keys)

    def get_all_status(self) -> List[Dict[str, Any]]:
        now = time.time()
        summary = []
        for i, kh in enumerate(self.keys):
            in_cd = kh.cooldown_until > now
            cd_left = max(0, int(kh.cooldown_until - now))
            summary.append({
                "Index": i + 1,
                "Provider": kh.provider.upper(),
                "Key": kh.preview,
                "Status": f"⏳ Cooldown ({cd_left}s)" if in_cd else "🟢 Ready",
                "Success": kh.success_count,
                "Errors": kh.error_count
            })
        return summary

    def get_candidate_key(self) -> Tuple[Optional[KeyHealth], int]:
        """Returns the next available key and its 1-based index."""
        if not self.keys:
            return None, 0
        now = time.time()
        total = len(self.keys)
        # Try finding one not in cooldown starting from current_idx
        for offset in range(total):
            idx = (self.current_idx + offset) % total
            candidate = self.keys[idx]
            if candidate.is_available:
                self.current_idx = idx
                return candidate, idx + 1
        # If all keys are in cooldown, pick the one with earliest cooldown expiry
        earliest_idx = min(range(total), key=lambda i: self.keys[i].cooldown_until)
        self.current_idx = earliest_idx
        return self.keys[earliest_idx], earliest_idx + 1

    def mark_key_failed(self, kh: KeyHealth, cooldown_seconds: float = 90.0):
        kh.cooldown_until = time.time() + cooldown_seconds
        kh.error_count += 1
        # Advance index to next key
        self.current_idx = (self.current_idx + 1) % max(1, len(self.keys))

    def mark_key_success(self, kh: KeyHealth):
        kh.success_count += 1
        kh.cooldown_until = 0.0
        # Alternating round-robin: rotate to the next healthy key for the next chunk
        if len(self.keys) > 1:
            self.current_idx = (self.current_idx + 1) % len(self.keys)

# Global singleton
GLOBAL_KEY_MANAGER = MultiKeyManager()

# =====================================================================
# INFERENCE DISPATCHERS (GEMINI, GROQ, OPENROUTER)
# =====================================================================

def call_gemini(api_key: str, prompt: str, model: str = "gemini-2.5-flash-lite") -> str:
    if genai is None:
        raise ImportError("google-genai package is not installed.")
    client = genai.Client(api_key=api_key)
    res = client.models.generate_content(
        model=model or "gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.1
        )
    )
    return res.text

def call_groq(api_key: str, prompt: str, model: str = "openai/gpt-oss-120b") -> str:
    if Groq is None:
        raise ImportError("groq package is not installed.")
    client = Groq(api_key=api_key)
    target_model = model if model and "/" in model else "openai/gpt-oss-120b"
    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        model=target_model,
        response_format={"type": "json_object"},
        temperature=0.1
    )
    return chat_completion.choices[0].message.content

def call_openrouter(api_key: str, prompt: str, model: str = "deepseek/deepseek-r1") -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "UGC NET JRF Solver"
    }
    headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model if "/" in model else "deepseek/deepseek-r1",
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    with httpx.Client(timeout=90.0) as client:
        resp = client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

def clean_and_parse_json(raw_text: str) -> List[Dict[str, Any]]:
    """Strips markdown fences and parses JSON robustly."""
    t = raw_text.strip()
    if t.startswith("```json"):
        t = t[7:]
    elif t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()

    # If model enclosed in { "questions": [...] }
    parsed = json.loads(t)
    if isinstance(parsed, list):
        return parsed
    elif isinstance(parsed, dict):
        if "questions" in parsed and isinstance(parsed["questions"], list):
            return parsed["questions"]
        elif "solutions" in parsed and isinstance(parsed["solutions"], list):
            return parsed["solutions"]
        return [parsed]
    return []

# =====================================================================
# MULTI-KEY FAILOVER CALLER
# =====================================================================

def dispatch_with_multi_key_failover(
    prompt: str,
    key_manager: MultiKeyManager,
    preferred_model: str = "gemini-2.5-flash-lite",
    status_callback: Optional[Callable[[str], None]] = None
) -> List[Dict[str, Any]]:
    """
    Dispatches request across the pool of 5-10 API keys.
    If Key 1 hits a rate limit or quota exhaustion, it marks it on cooldown
    and immediately shifts to Key 2, Key 3, etc.
    """
    total_keys = key_manager.total_keys()
    if total_keys == 0:
        raise ValueError("No API keys found. Please provide at least one Gemini, Groq, or OpenRouter API key.")

    max_attempts = total_keys * 2  # Try each key up to twice
    for attempt in range(max_attempts):
        if is_stop_requested():
            raise InterruptedError("Stop requested while waiting for an API key.")
        candidate, key_num = key_manager.get_candidate_key()
        if not candidate:
            raise ValueError("No candidate key available.")

        while candidate.cooldown_until > time.time():
            wait_sec = candidate.cooldown_until - time.time()
            msg = f"All {total_keys} keys on cooldown. Waiting for Key #{key_num} to unlock..."
            if status_callback:
                status_callback(msg)
            time.sleep(min(wait_sec, 1.0))
            if is_stop_requested():
                raise InterruptedError("Stop requested while waiting for an API key.")
            candidate, key_num = key_manager.get_candidate_key()

        provider = candidate.provider
        key = candidate.key
        
        info_msg = f"Connecting via [{provider.upper()} Key #{key_num}/{total_keys} ({candidate.preview})]"
        if status_callback:
            status_callback(info_msg)

        try:
            if provider == "gemini":
                raw_response = call_gemini(key, prompt, model=preferred_model)
            elif provider == "groq":
                raw_response = call_groq(key, prompt, model="openai/gpt-oss-120b")
            elif provider == "openrouter":
                raw_response = call_openrouter(key, prompt, model="deepseek/deepseek-r1")
            else:
                raise ValueError(f"Unknown provider: {provider}")

            parsed = clean_and_parse_json(raw_response)
            key_manager.mark_key_success(candidate)
            return parsed

        except Exception as e:
            err_str = str(e)
            is_quota_or_rate = any(x in err_str.lower() for x in [
                "429", "resource_exhausted", "rate_limit", "quota", "too many requests", "rate limit"
            ])

            cd_time = 120.0 if "quota" in err_str.lower() else 45.0
            key_manager.mark_key_failed(candidate, cooldown_seconds=cd_time)

            warn_msg = f"⚠️ [{provider.upper()} Key #{key_num}] Hit {'Rate/Quota Limit' if is_quota_or_rate else 'Error'}: {err_str[:60]}. Auto-switching to next available key..."
            if status_callback:
                status_callback(warn_msg)
            print(warn_msg.encode("ascii", errors="backslashreplace").decode("ascii"))
            if is_stop_requested():
                raise InterruptedError("Stop requested after the current API request.")
            time.sleep(2.0)

    raise RuntimeError(f"All {total_keys} API keys in pool exhausted their limits.")

# =====================================================================
# PDF EXTRACTION & CHUNKING
# =====================================================================

def request_stop():
    with open(STOP_SIGNAL_FILE, "w", encoding="utf-8") as f:
        f.write(f"stopped at {datetime.now().isoformat()}")

def clear_stop_request():
    if os.path.exists(STOP_SIGNAL_FILE):
        try:
            os.remove(STOP_SIGNAL_FILE)
        except OSError:
            pass

def is_stop_requested() -> bool:
    return os.path.exists(STOP_SIGNAL_FILE)

def load_checkpoint(output_file: str = OUTPUT_FILE_DEFAULT) -> List[Dict[str, Any]]:
    if not os.path.exists(output_file):
        return []
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    raise ValueError(f"Checkpoint '{output_file}' must contain a JSON object or array.")

def save_checkpoint(data: List[Dict[str, Any]], output_file: str = OUTPUT_FILE_DEFAULT):
    temp_file = output_file + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if os.path.exists(output_file):
        os.replace(temp_file, output_file)
    else:
        os.rename(temp_file, output_file)

def extract_text_from_pdf(pdf_path: str) -> str:
    if pymupdf is not None:
        with pymupdf.open(pdf_path) as document:
            pages = []
            for index, page in enumerate(document):
                text = page.get_text("text", sort=True)
                if text.strip():
                    pages.append(f"\n--- [Page {index + 1}] ---\n{text}")
        if pages:
            return "\n".join(pages)

    reader = PdfReader(pdf_path)
    full_text = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                full_text.append(f"\n--- [Page {i+1}] ---\n" + text)
        except Exception as e:
            print(f"Error reading page {i+1} of {pdf_path}: {e}")
    return "\n".join(full_text)


def _split_page_into_question_groups(page_text: str, chunk_size: int) -> List[str]:
    question_starts = list(QUESTION_START_RE.finditer(page_text))
    if len(question_starts) < 2:
        if len(page_text) > chunk_size:
            return chunk_text(page_text, chunk_size=chunk_size, overlap=0)
        return [page_text]

    prefix = page_text[:question_starts[0].start()].strip()
    groups = []
    for index, match in enumerate(question_starts):
        end = question_starts[index + 1].start() if index + 1 < len(question_starts) else len(page_text)
        group = page_text[match.start():end].strip()
        if index == 0 and prefix:
            group = f"{prefix}\n{group}"
        groups.append(group)

    split_groups = []
    for group in groups:
        if len(group) <= chunk_size:
            split_groups.append(group)
        else:
            split_groups.extend(chunk_text(group, chunk_size=chunk_size, overlap=0))
    return split_groups


def chunk_pdf_text(text: str, chunk_size: int = 4000) -> List[str]:
    """Keep PDF pages and detected question boundaries intact where possible."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero.")
    if not text.strip():
        return []

    pages = re.split(r"(?=--- \[Page \d+\] ---)", text)
    usable_pages = [
        page for page in pages
        if page.strip() and not re.search(
            r"instructions for the candidates|signature and name of invigilator",
            page,
            re.IGNORECASE,
        )
    ]
    segments = _split_page_into_question_groups("\n".join(usable_pages), chunk_size)

    chunks = []
    current = ""
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        separator = "\n\n" if current else ""
        if current and len(current) + len(separator) + len(segment) > chunk_size:
            chunks.append(current)
            current = segment
        else:
            current += separator + segment
    if current:
        chunks.append(current)
    return chunks


def question_numbers_in_text(text: str) -> List[str]:
    numbers = []
    for match in QUESTION_START_RE.finditer(text):
        number = re.search(r"\d+", match.group())
        if number:
            numbers.append(number.group())
    return numbers


def chunk_text(text: str, chunk_size: int = 4000, overlap: int = 300) -> List[str]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size.")
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])
        if end >= text_len:
            break
        start += chunk_size - overlap
    return chunks

def deduplicate_solutions(solutions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_texts = set()
    unique = []
    for item in solutions:
        if not isinstance(item, dict):
            continue
        q_text = str(item.get("question_text", item.get("question", ""))).strip()
        norm_key = re.sub(r"\s+", " ", q_text).casefold()
        if not norm_key or norm_key in seen_texts:
            continue
        seen_texts.add(norm_key)
        unique.append(item)
    return unique

# =====================================================================
# BATCH EXECUTION PIPELINE
# =====================================================================

def process_single_pdf(
    pdf_path: str,
    key_manager: MultiKeyManager,
    model: str = "gemini-2.5-flash-lite",
    chunk_size: int = 4000,
    inter_request_delay: float = 3.0,
    existing_entry: Optional[Dict[str, Any]] = None,
    on_chunk_completed: Optional[Callable[[Dict[str, Any]], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    filename = os.path.basename(pdf_path)
    chunking_version = 2
    if existing_entry is None:
        entry = {
            "filename": filename,
            "status": "in_progress",
            "total_chunks": 0,
            "processed_chunks": [],
            "solutions": [],
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
    else:
        entry = existing_entry
        entry.setdefault("solutions", [])
        entry.setdefault("processed_chunks", [])
        entry.setdefault("status", "in_progress")

    if entry.get("chunking_version") != chunking_version or entry.get("chunk_size") != chunk_size:
        if entry.get("chunking_version") is None and entry.get("solutions"):
            entry["legacy_solutions"] = entry["solutions"]
            entry["solutions"] = []
        entry["processed_chunks"] = []
        entry["failed_chunks"] = {}
        entry["status"] = "in_progress"
        entry.pop("last_error", None)
    entry["chunking_version"] = chunking_version
    entry["chunk_size"] = chunk_size

    if entry.get("status") == "completed" and not entry.get("failed_chunks"):
        if status_callback:
            status_callback(f"Paper {filename} already completed. Skipping.")
        return entry

    if status_callback:
        status_callback(f"Extracting text from {filename}...")

    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text.strip():
        entry["status"] = "needs_ocr"
        entry["last_error"] = "No selectable text was extracted from this PDF. OCR is required."
        entry["last_updated"] = datetime.now().isoformat()
        if status_callback:
            status_callback(f"No selectable text found in {filename}; OCR is required.")
        if on_chunk_completed:
            on_chunk_completed(entry)
        return entry

    chunks = chunk_pdf_text(raw_text, chunk_size=chunk_size)
    entry["total_chunks"] = len(chunks)
    processed_set = set(entry.get("processed_chunks", []))
    failed_chunks = entry.setdefault("failed_chunks", {})

    for c_idx, chunk in enumerate(chunks):
        if is_stop_requested():
            if status_callback:
                status_callback("Pause requested by user. Halting execution gracefully.")
            entry["last_updated"] = datetime.now().isoformat()
            if on_chunk_completed:
                on_chunk_completed(entry)
            return entry

        if c_idx in processed_set:
            if on_progress:
                on_progress(c_idx + 1, len(chunks), f"Already processed chunk {c_idx+1}/{len(chunks)}: {filename}")
            continue

        prompt = f"""Raw Exam Paper Text Chunk ({c_idx+1}/{len(chunks)}):
----------------------------------------
{chunk}
----------------------------------------
Carefully extract all UGC NET CS questions with full solutions, derivations, and distractor analyses according to your system instructions."""

        try:
            extracted_questions = dispatch_with_multi_key_failover(
                prompt=prompt,
                key_manager=key_manager,
                preferred_model=model,
                status_callback=status_callback
            )

            if not all(isinstance(question, dict) for question in extracted_questions):
                raise ValueError("The model response contained a non-object question entry.")
            for question in extracted_questions:
                if "question" in question and "question_text" not in question:
                    question["question_text"] = question["question"]
                if not str(question.get("question_text", "")).strip():
                    raise ValueError("The model returned a question without its question text.")
                if not str(question.get("correct_option", "")).strip():
                    raise ValueError("The model returned a question without a correct answer.")
                if not str(question.get("explanation", "")).strip():
                    raise ValueError("The model returned a question without an explanation.")
            expected_numbers = set(question_numbers_in_text(chunk))
            if expected_numbers:
                returned_numbers = set()
                for question in extracted_questions:
                    number = re.search(r"\d+", str(question.get("question_number", "")))
                    if number:
                        returned_numbers.add(number.group())
                missing_numbers = expected_numbers - returned_numbers
                if missing_numbers:
                    missing = ", ".join(sorted(missing_numbers, key=int))
                    raise ValueError(f"The model omitted numbered questions: {missing}.")
            if not extracted_questions and QUESTION_START_RE.search(chunk):
                raise ValueError("The model returned no questions for a chunk containing numbered questions.")

            entry["solutions"].extend(extracted_questions)
            entry["solutions"] = deduplicate_solutions(entry["solutions"])
            entry["processed_chunks"].append(c_idx)
            failed_chunks.pop(str(c_idx), None)
            entry["last_updated"] = datetime.now().isoformat()

            if on_chunk_completed:
                on_chunk_completed(entry)

            time.sleep(inter_request_delay)

        except Exception as e:
            if status_callback:
                status_callback(f"Chunk {c_idx+1} error: {e}")
            if is_stop_requested():
                entry["last_updated"] = datetime.now().isoformat()
                if on_chunk_completed:
                    on_chunk_completed(entry)
                return entry
            entry["last_error"] = str(e)
            failed_chunks[str(c_idx)] = str(e)
            entry["last_updated"] = datetime.now().isoformat()
            if on_chunk_completed:
                on_chunk_completed(entry)

        if on_progress:
            on_progress(c_idx + 1, len(chunks), f"Processed chunk {c_idx+1}/{len(chunks)}: {filename}")

    processed_set = set(entry["processed_chunks"])
    if len(processed_set) >= entry["total_chunks"] and not failed_chunks and entry["total_chunks"] > 0:
        entry["status"] = "completed"
        entry.pop("last_error", None)
        if status_callback:
            status_callback(f"Finished processing {filename}! Extracted {len(entry['solutions'])} questions.")
    elif failed_chunks:
        entry["status"] = "failed"
    else:
        entry["status"] = "in_progress"

    entry["last_updated"] = datetime.now().isoformat()
    if on_chunk_completed:
        on_chunk_completed(entry)
    return entry

def run_solver_batch(
    key_manager: Optional[MultiKeyManager] = None,
    pdf_dir: str = PDF_DIR_DEFAULT,
    output_file: str = OUTPUT_FILE_DEFAULT,
    model: str = "gemini-2.5-flash-lite",
    chunk_size: int = 4000,
    inter_request_delay: float = 3.0,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    status_callback: Optional[Callable[[str], None]] = None
) -> List[Dict[str, Any]]:
    clear_stop_request()
    km = key_manager or GLOBAL_KEY_MANAGER

    all_data = load_checkpoint(output_file)
    data_map = {item["filename"]: item for item in all_data if isinstance(item, dict) and "filename" in item}

    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir, exist_ok=True)

    all_pdf_files = sorted([f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")])
    if not all_pdf_files:
        if status_callback:
            status_callback(f"No PDF question papers found in '{pdf_dir}/'. Please upload papers first.")
        return all_data

    total_files = len(all_pdf_files)

    def handle_chunk_save(updated_entry: Dict[str, Any]):
        data_map[updated_entry["filename"]] = updated_entry
        save_checkpoint(list(data_map.values()), output_file)

    for idx, filename in enumerate(all_pdf_files):
        if is_stop_requested():
            if status_callback:
                status_callback("Execution halted by user request.")
            break

        full_path = os.path.join(pdf_dir, filename)
        existing_entry = data_map.get(filename)

        if (
            existing_entry
            and existing_entry.get("status") == "completed"
            and existing_entry.get("chunking_version") == 2
            and existing_entry.get("chunk_size") == chunk_size
            and not existing_entry.get("failed_chunks")
        ):
            if on_progress:
                on_progress(idx + 1, total_files, f"Already completed: {filename}")
            continue

        if on_progress:
            on_progress(idx, total_files, f"Processing file {idx+1}/{total_files}: {filename}")

        def report_chunk_progress(current_chunk, chunk_count, message):
            if on_progress:
                total_units = total_files * 1000
                current_units = idx * 1000 + round(1000 * current_chunk / max(chunk_count, 1))
                on_progress(current_units, total_units, message)

        updated_entry = process_single_pdf(
            pdf_path=full_path,
            key_manager=km,
            model=model,
            chunk_size=chunk_size,
            inter_request_delay=inter_request_delay,
            existing_entry=existing_entry,
            on_chunk_completed=handle_chunk_save,
            status_callback=status_callback,
            on_progress=report_chunk_progress,
        )

        data_map[filename] = updated_entry
        save_checkpoint(list(data_map.values()), output_file)

        if on_progress:
            on_progress(idx + 1, total_files, f"Completed/Checkpoint saved: {filename}")

        if is_stop_requested():
            if status_callback:
                status_callback("Execution halted by user request.")
            break

    return list(data_map.values())
