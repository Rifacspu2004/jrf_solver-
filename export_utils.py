"""
Data Export and Transformation Utilities for UGC NET JRF Question Bank
Generates:
- Formatted CSV (compatible with Excel, Pandas, and Flashcards)
- High-yield Markdown Study Guide (formatted for students with LaTeX math & full derivations)
"""

import json
import pandas as pd
from typing import List, Dict, Any

def convert_to_dataframe(dataset: List[Dict[str, Any]]) -> pd.DataFrame:
    """Flattens nested dataset into a structured pandas DataFrame."""
    rows = []
    for paper in dataset:
        filename = paper.get("filename", "Unknown Paper")
        solutions = paper.get("solutions", [])
        for idx, sol in enumerate(solutions):
            q_num = sol.get("question_number", idx + 1)
            q_text = sol.get("question_text", sol.get("question", ""))
            correct_opt = sol.get("correct_option", "")
            topic = sol.get("unit_topic", sol.get("topic", "General CS"))
            explanation = sol.get("explanation", "")
            distractor = sol.get("distractor_analysis", "")
            tip = sol.get("formula_or_exam_tip", "")
            
            # Format options string
            opts = sol.get("options", {})
            if isinstance(opts, dict):
                options_str = " | ".join([f"({k}) {v}" for k, v in opts.items()])
            elif isinstance(opts, list):
                options_str = " | ".join([f"({i+1}) {v}" for i, v in enumerate(opts)])
            else:
                options_str = str(opts)

            rows.append({
                "Paper / Source": filename,
                "Question No": q_num,
                "Unit / Topic": topic,
                "Question Statement": q_text,
                "Options": options_str,
                "Correct Answer": correct_opt,
                "Step-by-Step Explanation": explanation,
                "Distractor / Why Other Options Are Wrong": distractor,
                "Key Formulas & Notes": tip
            })
    return pd.DataFrame(rows)

def generate_markdown_study_notes(dataset: List[Dict[str, Any]]) -> str:
    """Generates an exam-ready, formatted Markdown document for students."""
    lines = [
        "# 🎓 UGC NET Computer Science & Applications (Subject 87)",
        "## JRF Comprehensive PYQ Master Guide & Solutions (2017 – 2026)",
        "",
        "> **Note for Aspirants:** Every solution contains step-by-step derivations, official NTA answer alignments, and distractor analyses for high-yield exam preparation.",
        "",
        "---",
        ""
    ]
    
    total_q = sum(len(p.get("solutions", [])) for p in dataset)
    lines.append(f"**Total Questions Solved:** {total_q} questions across {len(dataset)} papers.\n")
    
    for paper in dataset:
        filename = paper.get("filename", "Unknown Paper")
        solutions = paper.get("solutions", [])
        if not solutions:
            continue
            
        lines.append(f"\n## 📄 Examination Paper: `{filename}`")
        lines.append(f"*(Total Questions: {len(solutions)})*\n")
        
        for idx, sol in enumerate(solutions):
            q_num = sol.get("question_number", idx + 1)
            q_text = sol.get("question_text", sol.get("question", ""))
            correct_opt = sol.get("correct_option", "")
            topic = sol.get("unit_topic", sol.get("topic", "General CS"))
            explanation = sol.get("explanation", "")
            distractor = sol.get("distractor_analysis", "")
            tip = sol.get("formula_or_exam_tip", "")
            opts = sol.get("options", {})

            lines.append(f"### Q{q_num}. {topic}")
            lines.append(f"**Question:**\n> {q_text}\n")
            
            if opts:
                lines.append("**Options:**")
                if isinstance(opts, dict):
                    for k, v in opts.items():
                        lines.append(f"- **({k})** {v}")
                elif isinstance(opts, list):
                    for i, v in enumerate(opts):
                        lines.append(f"- **({i+1})** {v}")
                lines.append("")
                
            lines.append(f"✅ **Correct Option:** `{correct_opt}`\n")
            
            if explanation:
                lines.append("**💡 Detailed Derivation & Concept Explanation:**")
                lines.append(f"{explanation}\n")
                
            if distractor:
                lines.append("**❌ Distractor Analysis (Why other options are incorrect):**")
                lines.append(f"{distractor}\n")
                
            if tip:
                lines.append(f"> 📌 **High-Yield Exam Tip / Formula:** {tip}\n")
                
            lines.append("---\n")
            
    return "\n".join(lines)


def generate_pdf_study_guide(dataset: List[Dict[str, Any]]) -> bytes:
    """Create a printable PDF study guide from the saved question bank."""
    from io import BytesIO
    from os.path import dirname, join
    from xml.sax.saxutils import escape

    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    font_dir = join(dirname(reportlab.__file__), "fonts")
    regular_font = join(font_dir, "Vera.ttf")
    bold_font = join(font_dir, "VeraBd.ttf")
    if not pdfmetrics.getRegisteredFontNames() or "JRF-Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("JRF-Vera", regular_font))
        pdfmetrics.registerFont(TTFont("JRF-Vera-Bold", bold_font))

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "JRFTitle", parent=styles["Title"], fontName="JRF-Vera-Bold",
        alignment=TA_CENTER, fontSize=16, leading=20, textColor=colors.HexColor("#1E3A8A")
    )
    heading_style = ParagraphStyle(
        "JRFHeading", parent=styles["Heading2"], fontName="JRF-Vera-Bold",
        fontSize=12, leading=15, spaceBefore=12, spaceAfter=7,
        textColor=colors.HexColor("#1E3A8A")
    )
    body_style = ParagraphStyle(
        "JRFBody", parent=styles["BodyText"], fontName="JRF-Vera",
        fontSize=9, leading=12, spaceAfter=6, wordWrap="CJK"
    )
    answer_style = ParagraphStyle(
        "JRFAnswer", parent=body_style, fontName="JRF-Vera-Bold",
        textColor=colors.HexColor("#065F46")
    )

    def paragraph_text(value: Any) -> str:
        return escape(str(value)).replace("\n", "<br/>")

    story = [
        Paragraph("UGC NET Computer Science &amp; Applications", title_style),
        Paragraph("JRF Previous-Year Questions: Solved Study Guide", title_style),
        Spacer(1, 14),
        Paragraph(
            f"Saved questions: {sum(len(p.get('solutions', [])) for p in dataset)}"
            f" across {len(dataset)} papers.",
            body_style
        ),
    ]

    has_written_paper = False
    for paper in dataset:
        solutions = paper.get("solutions", [])
        if not solutions:
            continue
        if has_written_paper:
            story.append(PageBreak())
        has_written_paper = True
        story.append(Paragraph(f"Paper: {paragraph_text(paper.get('filename', 'Unknown'))}", heading_style))
        for index, solution in enumerate(solutions, start=1):
            number = solution.get("question_number", index)
            topic = solution.get("unit_topic", solution.get("topic", "UGC NET CS"))
            question = solution.get("question_text", solution.get("question", ""))
            story.append(Paragraph(f"Q{paragraph_text(number)}. {paragraph_text(topic)}", heading_style))
            if question:
                story.append(Paragraph(f"<b>Question:</b><br/>{paragraph_text(question)}", body_style))

            options = solution.get("options", {})
            if isinstance(options, dict):
                option_lines = [f"({key}) {value}" for key, value in options.items()]
            elif isinstance(options, list):
                option_lines = [f"({option_index}) {value}" for option_index, value in enumerate(options, start=1)]
            else:
                option_lines = [str(options)] if options else []
            if option_lines:
                story.append(Paragraph(
                    "<b>Options:</b><br/>" + "<br/>".join(paragraph_text(line) for line in option_lines),
                    body_style
                ))

            answer = solution.get("correct_option", "")
            if answer:
                story.append(Paragraph(f"Correct answer: {paragraph_text(answer)}", answer_style))
            for label, key in (
                ("Explanation", "explanation"),
                ("Why the other options are incorrect", "distractor_analysis"),
                ("Exam tip", "formula_or_exam_tip"),
            ):
                value = solution.get(key, "")
                if value:
                    story.append(Paragraph(f"<b>{label}:</b><br/>{paragraph_text(value)}", body_style))
            story.append(Spacer(1, 8))

    output = BytesIO()

    def add_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont("JRF-Vera", 8)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawRightString(A4[0] - 36, 20, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=42,
        bottomMargin=36,
        title="UGC NET JRF Solved Question Bank",
        author="UGC NET JRF AI Solver",
    )
    document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return output.getvalue()
