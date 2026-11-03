import pypdf
import re

pdf_path = "pyq_sources/UGC NET Paper 3_ Computer Science Nov 2017 English.pdf"
reader = pypdf.PdfReader(pdf_path)

print(f"Total Pages in PDF: {len(reader.pages)}")
all_found = []

for idx, page in enumerate(reader.pages):
    text = page.extract_text() or ""
    # Find question numbers like "\n1. ", "\n2. ", ... "\n75. "
    matches = re.findall(r'(?:^|\n)\s*(\d{1,3})\.\s+(.+)', text)
    if matches:
        q_nums = [m[0] for m in matches if int(m[0]) <= 150]
        print(f"Page {idx+1}: Found Questions {q_nums}")
        all_found.extend(q_nums)

print(f"\nTotal Questions detected across all pages: {len(all_found)}")
print(f"Question sequence: {all_found[:15]} ... {all_found[-10:]}")

