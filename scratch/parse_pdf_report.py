import pypdf

reader = pypdf.PdfReader("September_2026_Recruitment_Requirements_Report.pdf")
full_text = ""
for i, page in enumerate(reader.pages):
    full_text += f"\n--- Page {i+1} ---\n" + page.extract_text()

with open("scratch/pdf_text.txt", "w", encoding="utf-8") as f:
    f.write(full_text)

print(f"Extracted {len(full_text)} characters from PDF.")
print("PDF Search for Accenture and LTTS:")
for line in full_text.split("\n"):
    if "accenture" in line.lower() or "ltts" in line.lower() or "total" in line.lower() or "summary" in line.lower():
        print(line[:120])
