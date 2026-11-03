import pymupdf
import re

doc = pymupdf.open('pyq_sources/UGC NET Paper 3_ Computer Science Nov 2017 English.pdf')
all_q = []
for i in range(2, len(doc)-1):
    t = doc[i].get_text()
    # Match patterns like "\n1.\n", "\n2.\n" or "1. In..."
    matches = re.findall(r'(?:^|\n)\s*(\d{1,2})\.\s*(?:\n|[A-Z])', t)
    all_q.extend(matches)
    print(f"Page {i+1}: {matches}")

print("Total detected questions:", len(all_q), "Unique:", len(set(all_q)))
print("Numbers found:", sorted([int(x) for x in set(all_q)]))

