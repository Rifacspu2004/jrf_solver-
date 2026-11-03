"""
Generates a realistic UGC NET Computer Science (Subject 87) sample PYQ PDF.
"""
from fpdf import FPDF
import os

class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 14)
        self.cell(0, 10, 'UGC NET June 2024 - Computer Science & Applications (Subject Code 87)', border=False, align='C', new_x="LMARGIN", new_y="NEXT")
        self.set_font('Helvetica', 'I', 10)
        self.cell(0, 8, 'Official PYQ Paper - University Grants Commission National Eligibility Test (JRF)', border=False, align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

def generate_sample_pyq():
    os.makedirs("pyq_sources", exist_ok=True)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    questions = [
        (
            "Q1. Consider the following scheduling algorithms: (I) First-Come, First-Served (FCFS), (II) Shortest Job First (non-preemptive), (III) Round Robin (RR), (IV) Shortest Remaining Time First (SRTF). Which of the above scheduling algorithms are non-preemptive?",
            ["(1) (I) and (II) only", "(2) (I), (II) and (IV) only", "(3) (II) and (III) only", "(4) (I) and (IV) only"]
        ),
        (
            "Q2. In relational database theory, which of the following is NOT one of Codd's fundamental relational algebra operators?",
            ["(1) Selection", "(2) Projection", "(3) Natural Join", "(4) Cartesian Product"]
        ),
        (
            "Q3. The language L = {a^n b^n c^n | n >= 1} is:",
            ["(1) Regular", "(2) Context-Free but not regular", "(3) Context-Sensitive but not context-free", "(4) Not recursively enumerable"]
        ),
        (
            "Q4. What is the worst-case time complexity of searching an element in a balanced AVL search tree with n keys?",
            ["(1) O(1)", "(2) O(log n)", "(3) O(n)", "(4) O(n log n)"]
        ),
        (
            "Q5. An IPv4 datagram has arrived with the first 8 bits having the hexadecimal value 45. What is the header length in bytes?",
            ["(1) 5 bytes", "(2) 20 bytes", "(3) 45 bytes", "(4) 40 bytes"]
        )
    ]

    for q_text, opts in questions:
        pdf.set_font("Helvetica", 'B', 11)
        pdf.multi_cell(0, 7, q_text)
        pdf.ln(2)
        pdf.set_font("Helvetica", '', 10)
        for opt in opts:
            pdf.cell(0, 6, f"   {opt}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    output_path = "pyq_sources/ugc_net_cs_2024_sample.pdf"
    pdf.output(output_path)
    print(f"Sample PYQ PDF generated successfully at {output_path}")

if __name__ == "__main__":
    generate_sample_pyq()
