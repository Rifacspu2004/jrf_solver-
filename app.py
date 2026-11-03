"""
🎓 UGC NET Computer Science & Applications (Subject Code 87)
JRF PYQ AI Engine & Student Solution Portal (2017–2026)
Multi-Key (5-10 Keys) & Multi-Provider Auto-Failover Edition
"""

import os
import json
import hashlib
import threading
import streamlit as st
import pandas as pd
from datetime import datetime

from solver_core import (
    OUTPUT_FILE_DEFAULT,
    PDF_DIR_DEFAULT,
    load_checkpoint,
    request_stop,
    clear_stop_request,
    is_stop_requested,
    run_solver_batch,
    GLOBAL_KEY_MANAGER,
    UGC_NET_UNITS
)
from export_utils import (
    convert_to_dataframe,
    generate_markdown_study_notes,
    generate_pdf_study_guide,
)

# Page Configuration
st.set_page_config(
    page_title="UGC NET JRF CS - Multi-Key AI Solver",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header { font-size: 2.1rem; font-weight: 800; color: #1E3A8A; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.0rem; color: #4B5563; margin-bottom: 1.2rem; }
    .key-badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 5px;
    }
    .badge-gemini { background-color: #E0E7FF; color: #3730A3; }
    .badge-groq { background-color: #FEF3C7; color: #92400E; }
    .badge-openrouter { background-color: #EDE9FE; color: #5B21B6; }
    .question-card {
        background-color: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }
    .correct-opt-box {
        background-color: #ECFDF5;
        border-left: 4px solid #10B981;
        padding: 12px;
        margin: 10px 0;
        border-radius: 6px;
        color: #065F46;
        font-weight: 600;
    }
    .distractor-box {
        background-color: #FEF2F2;
        border-left: 4px solid #EF4444;
        padding: 12px;
        margin: 10px 0;
        border-radius: 6px;
        color: #991B1B;
    }
    .explanation-box {
        background-color: #EFF6FF;
        border-left: 4px solid #3B82F6;
        padding: 14px;
        margin: 10px 0;
        border-radius: 6px;
    }
    .tip-box {
        background-color: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 10px;
        margin: 8px 0;
        border-radius: 6px;
        font-size: 0.92rem;
    }
</style>
""", unsafe_allow_html=True)

os.makedirs(PDF_DIR_DEFAULT, exist_ok=True)

# Helper to save keys to .env
def save_keys_to_env(gem_keys: str, groq_keys: str, or_keys: str):
    lines = [
        "# =====================================================================",
        "# UGC NET CS JRF Solver - Multi-Key Pool Configuration",
        "# =====================================================================",
        f"GEMINI_API_KEYS={gem_keys.strip()}",
        f"GROQ_API_KEYS={groq_keys.strip()}",
        f"OPENROUTER_API_KEYS={or_keys.strip()}"
    ]
    with open(".env", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _update_job(job_state, message):
    with job_state["lock"]:
        job_state["status"] = message
        job_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        job_state["logs"] = job_state["logs"][-10:]


def _run_solver_in_background(job_state, model, chunk_size, rate_delay):
    def update_progress(current, total, message):
        with job_state["lock"]:
            job_state["progress"] = min(max(current / max(total, 1), 0.0), 1.0)
            job_state["status"] = message
            job_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
            job_state["logs"] = job_state["logs"][-10:]

    try:
        result = run_solver_batch(
            key_manager=GLOBAL_KEY_MANAGER,
            pdf_dir=PDF_DIR_DEFAULT,
            output_file=OUTPUT_FILE_DEFAULT,
            model=model,
            chunk_size=chunk_size,
            inter_request_delay=rate_delay,
            on_progress=update_progress,
            status_callback=lambda message: _update_job(job_state, message),
        )
        stopped = is_stop_requested()
        has_failures = any(
            paper.get("status") in {"failed", "needs_ocr"}
            for paper in result
        )
        with job_state["lock"]:
            job_state["completion"] = (
                "paused" if stopped else "completed_with_errors" if has_failures else "completed"
            )
            job_state["status"] = (
                "Paused; checkpoint saved."
                if stopped
                else "Batch finished with failed papers; check status and retry."
                if has_failures
                else "All papers processed."
            )
            job_state["refresh_needed"] = True
    except Exception as exc:
        with job_state["lock"]:
            job_state["completion"] = "error"
            job_state["status"] = f"Execution error: {exc}"
            job_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {job_state['status']}")
            job_state["logs"] = job_state["logs"][-10:]
            job_state["refresh_needed"] = True
    finally:
        with job_state["lock"]:
            job_state["running"] = False
        clear_stop_request()


@st.fragment(run_every="2s")
def render_execution_controls(model, chunk_size, rate_delay, has_pdfs):
    job = st.session_state.solver_job
    col_start, col_stop = st.columns(2)
    with col_start:
        start_clicked = st.button(
            "▶️ Start / Resume",
            type="primary",
            use_container_width=True,
            disabled=job["running"],
            key="solver_start",
        )
    with col_stop:
        stop_clicked = st.button(
            "⏸️ Stop / Pause",
            type="secondary",
            use_container_width=True,
            disabled=not job["running"],
            key="solver_stop",
        )

    if start_clicked:
        if GLOBAL_KEY_MANAGER.total_keys() == 0:
            st.error("No API keys configured. Add a key in the sidebar first.")
        elif not has_pdfs:
            st.error("No PDF files found in pyq_sources/. Upload papers first.")
        else:
            clear_stop_request()
            with job["lock"]:
                job["running"] = True
                job["completion"] = ""
                job["progress"] = 0.0
                job["refresh_needed"] = False
                job["full_refresh_done"] = False
                job["logs"] = []
            thread = threading.Thread(
                target=_run_solver_in_background,
                args=(job, model, chunk_size, rate_delay),
                daemon=True,
            )
            job["thread"] = thread
            thread.start()

    if stop_clicked:
        request_stop()
        _update_job(job, "Stop requested; waiting for the current API request to finish.")

    with job["lock"]:
        running = job["running"]
        status = job["status"]
        progress = job["progress"]
        logs = list(job["logs"])
        completion = job["completion"]
        refresh_needed = job["refresh_needed"]

    if running or status:
        st.progress(progress, text=status)
        if logs:
            st.code("\n".join(logs), language="text")
    if completion == "paused":
        st.warning(status)
    elif completion == "completed":
        st.success(status)
    elif completion == "error":
        st.error(status)
    elif completion == "completed_with_errors":
        st.warning(status)

    if refresh_needed and not job.get("full_refresh_done"):
        job["full_refresh_done"] = True
        st.rerun()


# --- Sidebar Controls ---
st.sidebar.title("🔑 Multi-Key Pool (5–10 Keys)")

with st.sidebar.expander("🛠️ Configure 5–10 API Keys", expanded=GLOBAL_KEY_MANAGER.total_keys() == 0):
    st.markdown("""
    **Provider key rotation**:
    Paste keys (one per line or comma-separated). When a request fails, the solver tries other configured keys.
    Provider quotas and availability can still interrupt a batch; failed chunks remain retryable.
    """)
    
    # Pre-populate from current manager
    cur_gem = "\n".join([k.key for k in GLOBAL_KEY_MANAGER.keys if k.provider == "gemini"])
    cur_groq = "\n".join([k.key for k in GLOBAL_KEY_MANAGER.keys if k.provider == "groq"])
    cur_or = "\n".join([k.key for k in GLOBAL_KEY_MANAGER.keys if k.provider == "openrouter"])

    input_gemini = st.text_area("Google Gemini Keys (Get free at aistudio.google.com)", value=cur_gem, height=90, help="Paste keys from 1 or more Google accounts")
    input_groq = st.text_area("Groq Cloud Keys (console.groq.com)", value=cur_groq, height=75, help="Optional fallback provider; model access and quotas vary.")
    input_or = st.text_area("OpenRouter Keys (Optional, openrouter.ai)", value=cur_or, height=60)

    if st.button("💾 Save & Sync Key Pool", use_container_width=True):
        gem_list = [k.strip() for k in input_gemini.replace(";", ",").replace("\n", ",").split(",") if k.strip()]
        groq_list = [k.strip() for k in input_groq.replace(";", ",").replace("\n", ",").split(",") if k.strip()]
        or_list = [k.strip() for k in input_or.replace(";", ",").replace("\n", ",").split(",") if k.strip()]

        GLOBAL_KEY_MANAGER.update_keys(gem_list, groq_list, or_list)
        save_keys_to_env(",".join(gem_list), ",".join(groq_list), ",".join(or_list))
        st.success(f"Synced {GLOBAL_KEY_MANAGER.total_keys()} keys across providers!")
        st.rerun()

# Real-time Key Pool Health Dashboard in Sidebar
st.sidebar.subheader(f"📊 Key Pool Status ({GLOBAL_KEY_MANAGER.total_keys()} Keys)")
key_statuses = GLOBAL_KEY_MANAGER.get_all_status()
if not key_statuses:
    st.sidebar.warning("⚠️ No API keys configured yet. Expand 'Configure 5–10 API Keys' above.")
else:
    for ks in key_statuses:
        p = ks["Provider"]
        badge_cls = "badge-gemini" if p == "GEMINI" else ("badge-groq" if p == "GROQ" else "badge-openrouter")
        st.sidebar.markdown(f"""
        <div style="font-size:0.85rem; margin-bottom:4px;">
            <span class="key-badge {badge_cls}">#{ks['Index']} {p}</span>
            <code>{ks['Key']}</code>: {ks['Status']}
            <span style="color:#6B7280; font-size:0.75rem;">(✅{ks['Success']} ❌{ks['Errors']})</span>
        </div>
        """, unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Solver Settings")

selected_model = st.sidebar.selectbox(
    "Primary Model",
    options=["gemini-2.5-flash-lite", "gemini-2.5-flash"],
    index=0,
    help="Gemini is used for Gemini keys; configured Groq and OpenRouter keys are used as fallback providers."
)

rate_delay = st.sidebar.slider(
    "Inter-Request Rate Delay (seconds)",
    min_value=1.0,
    max_value=10.0,
    value=5.0,
    step=0.5,
    help="Use a delay that complies with your provider's current quota; 5 seconds is a conservative starting point."
)

chunk_size = st.sidebar.slider(
    "PDF Chunk Size (Characters)",
    min_value=1000,
    max_value=6000,
    value=2500,
    step=500
)

st.sidebar.markdown("---")
st.sidebar.subheader("⏯️ Execution Controls")

if "solver_job" not in st.session_state:
    st.session_state.solver_job = {
        "running": False,
        "status": "",
        "completion": "",
        "progress": 0.0,
        "logs": [],
        "lock": threading.Lock(),
        "refresh_needed": False,
        "full_refresh_done": False,
        "thread": None,
    }

# --- Main App Header ---
st.markdown('<div class="main-header">🎓 UGC NET Computer Science JRF AI Engine</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Multi-Key Auto-Failover (5–10 Keys) • Zero Downtime • Deep Pedagogical Derivations</div>', unsafe_allow_html=True)

# Metrics
current_dataset = load_checkpoint(OUTPUT_FILE_DEFAULT)
all_pdfs = sorted([f for f in os.listdir(PDF_DIR_DEFAULT) if f.lower().endswith(".pdf")])
with st.sidebar:
    render_execution_controls(selected_model, chunk_size, rate_delay, bool(all_pdfs))
total_papers = len(all_pdfs)
completed_papers = sum(
    1 for paper in current_dataset
    if paper.get("status") == "completed"
    and paper.get("chunking_version") == 2
    and paper.get("chunk_size") == chunk_size
    and not paper.get("failed_chunks")
)
papers_needing_work = max(total_papers - completed_papers, 0)
total_questions = sum(
    1
    for paper in current_dataset
    for question in paper.get("solutions", [])
    if isinstance(question, dict)
    and question.get("correct_option")
    and question.get("explanation")
)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Total PYQ Papers", f"{total_papers} files")
with m2:
    st.metric("Completed Papers", f"{completed_papers} / {total_papers}")
with m3:
    st.metric("Papers Needing Work", f"{papers_needing_work}")
with m4:
    st.metric("Questions Solved", f"{total_questions} PYQs")

st.markdown("---")

tab_solve, tab_explore, tab_export, tab_keys = st.tabs([
    "🚀 Solver Dashboard & Upload",
    "📚 Question Bank & Student Explorer",
    "💾 Data Export & Downloads",
    "💡 Best API Keys & Free Quotas"
])

# ==========================================
# TAB 1: SOLVER DASHBOARD & UPLOAD
# ==========================================
with tab_solve:
    st.subheader("1. Upload PYQ Question Papers (2017–2026)")
    uploaded_files = st.file_uploader(
        "Upload UGC NET CS Question Paper PDFs",
        type=["pdf"],
        accept_multiple_files=True
    )
    if uploaded_files:
        saved_count = 0
        for uf in uploaded_files:
            target_path = os.path.join(PDF_DIR_DEFAULT, uf.name)
            if not os.path.exists(target_path):
                with open(target_path, "wb") as f:
                    f.write(uf.getbuffer())
                saved_count += 1
        if saved_count > 0:
            st.success(f"Added {saved_count} new PDF file(s) into `{PDF_DIR_DEFAULT}/`.")
            st.rerun()

    st.subheader("2. Workspace PDF Status & Checkpoints")
    if not all_pdfs:
        st.info("No PDF files in `pyq_sources/` yet. Upload your 2017–2026 PYQ papers above.")
    else:
        dataset_map = {p["filename"]: p for p in current_dataset if isinstance(p, dict) and "filename" in p}
        table_rows = []
        for f in all_pdfs:
            f_path = os.path.join(PDF_DIR_DEFAULT, f)
            size_kb = os.path.getsize(f_path) / 1024
            info = dataset_map.get(f)
            if info:
                if info.get("status") == "completed":
                    status = "✅ Completed"
                elif info.get("status") == "failed":
                    status = f"❌ Retry needed ({len(info.get('failed_chunks') or {})} failed chunks)"
                elif info.get("status") == "needs_ocr":
                    status = "⚠️ OCR required"
                else:
                    status = f"⏳ In Progress ({len(info.get('processed_chunks', []))}/{info.get('total_chunks', '?')} chunks)"
                q_count = len(info.get("solutions", []))
                last_mod = info.get("last_updated", "-")[:19]
            else:
                status = "⚪ Not Started"
                q_count = 0
                last_mod = "-"
                if info and info.get("status") == "completed":
                    status = "🔄 Checkpoint needs refresh"
                table_rows.append({
                "Paper Filename": f,
                "Size (KB)": f"{size_kb:.1f}",
                "Status": status,
                "Questions Extracted": q_count,
                "Last Updated": last_mod
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

# ==========================================
# TAB 2: STUDENT QUESTION BANK EXPLORER
# ==========================================
with tab_explore:
    st.subheader("📖 Interactive UGC NET JRF Question Explorer")
    st.markdown("Full step-by-step mathematical proofs, distractor analyses, and LaTeX formulas.")
    
    if not current_dataset or sum(len(p.get("solutions", [])) for p in current_dataset) == 0:
        st.info("No questions solved yet. Start the engine in Tab 1 to begin.")
    else:
        all_flattened_questions = []
        available_papers = []
        for paper in current_dataset:
            p_name = paper.get("filename", "Unknown")
            available_papers.append(p_name)
            for q in paper.get("solutions", []):
                q_copy = dict(q)
                q_copy["_paper"] = p_name
                all_flattened_questions.append(q_copy)

        f1, f2, f3 = st.columns([2, 1, 1])
        with f1:
            search_query = st.text_input("🔍 Search question, topic, formula, or concept", "")
        with f2:
            paper_filter = st.selectbox("Filter by Paper", options=["All Papers"] + available_papers)
        with f3:
            unit_filter = st.selectbox("Filter by Subject Unit", options=["All Units"] + UGC_NET_UNITS)

        filtered_qs = all_flattened_questions
        if paper_filter != "All Papers":
            filtered_qs = [q for q in filtered_qs if q.get("_paper") == paper_filter]
        if unit_filter != "All Units":
            unit_prefix = unit_filter.split(":")[0].strip().lower()
            filtered_qs = [q for q in filtered_qs if unit_prefix in str(q.get("unit_topic", "")).lower() or unit_filter.lower() in str(q.get("unit_topic", "")).lower()]
        if search_query.strip():
            sq = search_query.strip().lower()
            filtered_qs = [
                q for q in filtered_qs
                if sq in str(q.get("question_text", q.get("question", ""))).lower()
                or sq in str(q.get("explanation", "")).lower()
                or sq in str(q.get("unit_topic", "")).lower()
                or sq in str(q.get("formula_or_exam_tip", "")).lower()
            ]

        st.write(f"Showing **{len(filtered_qs)}** of **{len(all_flattened_questions)}** questions:")

        page_size = 10
        total_pages = max(1, (len(filtered_qs) + page_size - 1) // page_size)
        curr_page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
        start_idx = (curr_page - 1) * page_size
        end_idx = min(start_idx + page_size, len(filtered_qs))

        for q in filtered_qs[start_idx:end_idx]:
            q_num = q.get("question_number", "-")
            q_text = q.get("question_text", q.get("question", ""))
            correct_opt = q.get("correct_option", "")
            topic = q.get("unit_topic", q.get("topic", "UGC NET CS"))
            explanation = q.get("explanation", "")
            distractor = q.get("distractor_analysis", "")
            tip = q.get("formula_or_exam_tip", "")
            opts = q.get("options", {})
            paper_source = q.get("_paper", "")

            with st.container():
                st.markdown(f"""
                <div class="question-card">
                    <span style="background-color:#E0E7FF; color:#3730A3; padding:4px 8px; border-radius:4px; font-weight:600; font-size:0.85rem;">
                        📄 {paper_source} | Question {q_num}
                    </span>
                    <span style="background-color:#FEF3C7; color:#92400E; padding:4px 8px; border-radius:4px; font-weight:600; font-size:0.85rem; margin-left:8px;">
                        🎯 {topic}
                    </span>
                    <div style="font-size:1.15rem; font-weight:600; margin-top:14px; line-height:1.5;">
                        {q_text}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if opts:
                    st.markdown("**Options:**")
                    if isinstance(opts, dict):
                        for k, v in opts.items():
                            is_correct = str(k).strip() in str(correct_opt) or str(v).strip() in str(correct_opt)
                            st.markdown(f"{'✅' if is_correct else '🔘'} **({k})** {v}")
                    elif isinstance(opts, list):
                        for i, v in enumerate(opts):
                            st.markdown(f"🔘 **({i+1})** {v}")

                st.markdown(f"""
                <div class="correct-opt-box">
                    🎯 <b>Correct Answer:</b> {correct_opt}
                </div>
                """, unsafe_allow_html=True)

                if explanation:
                    st.markdown(f"""
                    <div class="explanation-box">
                        <b>💡 Step-by-Step Derivation & Reasoning:</b><br/>
                        {explanation}
                    </div>
                    """, unsafe_allow_html=True)

                if distractor:
                    st.markdown(f"""
                    <div class="distractor-box">
                        <b>❌ Distractor Analysis (Why Other Options are Incorrect):</b><br/>
                        {distractor}
                    </div>
                    """, unsafe_allow_html=True)

                if tip:
                    st.markdown(f"""
                    <div class="tip-box">
                        📌 <b>High-Yield Formula / Exam Pointer:</b> {tip}
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<hr style='margin:10px 0 25px 0;'>", unsafe_allow_html=True)

# ==========================================
# TAB 3: DATA EXPORTS
# ==========================================
with tab_export:
    st.subheader("💾 Export Solved Question Bank")
    if not current_dataset or sum(len(p.get("solutions", [])) for p in current_dataset) == 0:
        st.info("No data available to export yet.")
    else:
        df = convert_to_dataframe(current_dataset)
        json_str = json.dumps(current_dataset, indent=2, ensure_ascii=False)
        csv_str = df.to_csv(index=False).encode('utf-8')
        md_notes = generate_markdown_study_notes(current_dataset)
        pdf_signature = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
        if st.session_state.get("pdf_export_signature") != pdf_signature:
            st.session_state.pdf_export_data = None
            st.session_state.pdf_export_signature = pdf_signature

        d1, d2, d3, d4 = st.columns(4)
        with d1:
            st.download_button("📥 Download JSON (Master Dataset)", data=json_str, file_name="solved_jrf_output.json", mime="application/json", use_container_width=True)
        with d2:
            st.download_button("📊 Download CSV (Excel & Flashcards)", data=csv_str, file_name="solved_jrf_output.csv", mime="text/csv", use_container_width=True)
        with d3:
            st.download_button("📝 Download Markdown Study Guide", data=md_notes, file_name="ugc_net_jrf_study_notes.md", mime="text/markdown", use_container_width=True)
        with d4:
            if st.button("🛠️ Prepare Readable PDF", use_container_width=True):
                with st.spinner("Formatting the printable study guide..."):
                    st.session_state.pdf_export_data = generate_pdf_study_guide(current_dataset)
            if st.session_state.get("pdf_export_data"):
                st.download_button(
                    "📄 Download Readable PDF",
                    data=st.session_state.pdf_export_data,
                    file_name="ugc_net_jrf_study_guide.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

        st.markdown("---")
        st.dataframe(df.head(20), use_container_width=True)

# ==========================================
# TAB 4: BEST API KEYS GUIDE
# ==========================================
with tab_keys:
    st.subheader("💡 API Providers for Solving Your Question Bank")
    st.markdown("""
    Provider pricing, model availability, and request quotas change. Check each provider's current terms and limits before starting a large batch:
    
    ### 1. 🥇 Google Gemini AI Studio (Best Overall for Large Batches)
    - **How to get:** Go to [aistudio.google.com](https://aistudio.google.com), click **"Get API key"**, and copy it.
    - Configure keys you are authorized to use. The rate delay is configurable in the sidebar.

    ### 2. 🥈 Groq Cloud (Best for Deep Reasoning & Speed)
    - **How to get:** Go to [console.groq.com](https://console.groq.com), sign in with GitHub or email, and generate an API key.
    - **Model used by this solver:** `openai/gpt-oss-120b`.
    - **Availability:** Check the provider console for current model access and quotas.

    ### 3. 🥉 OpenRouter (Universal Backup)
    - **How to get:** Go to [openrouter.ai](https://openrouter.ai), click **"Keys"** and generate a free key.
    - **Availability:** Model pricing and free-tier availability vary by model and can change.

    ---
    ### 📁 Where to Upload Your Keys in Code:
    You can paste your keys directly into the **[`.env`](file:///d:/intern%20Project/JRF%20Problem%20solver/.env)** file:
    ```env
    GEMINI_API_KEYS=AIzaSyKey1,AIzaSyKey2,AIzaSyKey3,AIzaSyKey4,AIzaSyKey5
    GROQ_API_KEYS=gsk_key1,gsk_key2
    ```
    The engine reads `.env` automatically on startup!
    """)
