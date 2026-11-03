# 🎓 UGC NET Computer Science & Applications (Subject 87) - JRF PYQ AI Engine

An end-to-end, locally hosted, fault-tolerant AI Engine engineered to extract, solve, and generate comprehensive pedagogical explanations for **3,000+ UGC NET Computer Science & Applications (Subject Code 87) Previous Year Questions (PYQs) spanning 2017 to 2026**.

Built according to the **System Architecture & Technical Execution Blueprint**.

---

## 🌟 Key Architecture & Capabilities

1. **Detailed Pedagogical Explanations & Reasoning for Students**:
   - Every question includes the exact **Question Text**, **Options (1–4)**, **Correct Option**, and **UGC NET Syllabus Unit / Topic**.
   - **Step-by-step mathematical derivation / proof** for numerical and algorithmic questions.
   - **Distractor Analysis**: Thoroughly explains *why* each incorrect option is wrong, addressing common student misconceptions.
   - **High-Yield Exam Tips**: Concise shortcuts and exam pointers for quick recall.

2. **Continuous Processing, Pause & Resume**:
   - The Streamlit solver runs in a background worker, so one Start click processes all uploaded papers until completion or pause.
   - Successfully processed chunks are checkpointed in `solved_jrf_output.json`.
   - Failed chunks remain retryable and are not marked completed. Legacy answers are archived in the checkpoint while papers are reprocessed with the improved extractor.

3. **Provider Failover & Retry Visibility**:
   - Configurable delay between requests and key rotation across the configured providers.
   - Failed chunks are reported in the dashboard and retried on the next Start / Resume.
   - Provider limits and free-tier quotas vary; multiple keys do not guarantee uninterrupted service or bypass provider policies.

4. **Multi-Format Persistence & Exports**:
   - **JSON (`solved_jrf_output.json`)**: Master structured database conforming to the blueprint schema.
   - **CSV (`solved_jrf_output.csv`)**: Tabular export ready for Excel, data analysis, and Anki flashcard generation.
   - **Markdown (`ugc_net_jrf_study_notes.md`)**: Formatted study guide with LaTeX math ready to export or print.
   - **PDF (`ugc_net_jrf_study_guide.pdf`)**: Printable study guide with questions, options, answers, and explanations.

---

## 📁 Project Directory Structure

```text
d:/intern Project/JRF Problem solver/
│
├── pyq_sources/                     <-- Directory storing raw input PDF question papers (2017–2026)
│   ├── ugc_net_cs_2024_sample.pdf   <-- Included sample question paper
│   ├── ugc_net_cs_2023_dec.pdf
│   └── ...
│
├── app.py                           <-- Streamlit Web Application (UI, State & Explorer)
├── solver_core.py                   <-- PyMuPDF extraction, question-aware chunking, API and checkpoint engine
├── export_utils.py                  <-- CSV, Markdown and PDF study-guide generation utilities
├── cli_solver.py                    <-- Optional CLI batch runner for overnight processing
├── test_suite.py                    <-- Automated unit test suite verifying checkpoints & chunking
├── run_app.bat                      <-- 1-Click Windows Batch Launcher
├── requirements.txt                 <-- Project dependencies (Streamlit, Gemini, Groq, dotenv, PyMuPDF, ReportLab, pandas)
└── solved_jrf_output.json           <-- Persistent master output file containing solved datasets
```

---

## 🚀 Quick Start Guide

### Step 1: Launch the Web Dashboard
Install the requirements into the project's virtual environment first:
```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```
Double-click `run_app.bat` or run the following command in your terminal:
```bash
.venv\Scripts\python.exe -m streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### Step 2: Configure Settings in the Sidebar
1. Enter your **Google Gemini API Key** in the sidebar (or export `GEMINI_API_KEY="your_api_key"`).
2. Choose your preferred Gemini model (default: **`gemini-2.5-flash-lite`**).
3. Set the delay between API requests according to your provider's current quota.

### Step 3: Upload Papers & Start Solving
1. In **Tab 1 ("🚀 Solver Dashboard & Upload")**, drag and drop your UGC NET CS question paper PDFs (from 2017 to 2026).
2. Click **"▶️ Start / Resume"** once. The background worker continues through all uploaded papers.
3. You can click **"⏸️ Stop / Pause"** at any time.

### Step 4: Explore & Study in the Student Portal
1. Navigate to **Tab 2 ("📚 Question Bank & Student Explorer")**.
2. Search by keywords (e.g. *Dijkstra*, *Deadlock*, *Chomsky*, *IPv4*, *B-Tree*).
3. Filter by examination paper or by UGC NET Subject Unit (Units 1 to 10).
4. View correct answers, complete derivations, and distractor analyses.

### Step 5: Export Data
1. Navigate to **Tab 3 ("💾 Data Export & Downloads")**.
2. Download the JSON checkpoint, CSV, or Markdown guide. To get a PDF, click **Prepare Readable PDF**, then **Download Readable PDF**.

Scanned/image-only PDFs need OCR before the solver can read them; the dashboard marks these as **OCR required** instead of silently reporting completion. Check AI-generated answers against the official NTA key before exam use.

---

## 💻 Optional: Running via Command Line (CLI)

If you have a batch of 30+ papers with 3,000+ questions and wish to run them overnight in the terminal:
```bash
.venv\Scripts\python.exe cli_solver.py --api-key "YOUR_GEMINI_API_KEY"
```
- Press `Ctrl+C` at any time to pause safely.
- Rerun the command to resume immediately.

---

## 🎯 Answer Verification

The solver generates explanations from the supplied paper text; it does not automatically verify answers against NTA's official key or external references. Compare answers with the official key, especially where PDF extraction is unclear or a question is ambiguous.
