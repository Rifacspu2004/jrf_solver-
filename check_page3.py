import pypdf

pdf_path = "pyq_sources/UGC NET Paper 3_ Computer Science Nov 2017 English.pdf"
reader = pypdf.PdfReader(pdf_path)
page3_text = reader.pages[2].extract_text()
print("--- RAW TEXT OF PAGE 3 ---")
print(repr(page3_text))
print("--- PRINTED TEXT ---")
print(page3_text)

