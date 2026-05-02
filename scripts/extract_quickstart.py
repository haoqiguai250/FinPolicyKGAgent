"""Extract text from the Doubao quickstart PDF"""
import pdfplumber

pdf_path = r"D:\桌面\agent实验室项目\第三周\金融政策存放\火山方舟_快速入门_1775280154.pdf"
with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if text:
            # Write to file to avoid encoding issues
            with open(r"d:\WorkBuddy\FinPolicyKG\scripts\quickstart_text.txt", "a", encoding="utf-8") as f:
                f.write(f"\n\n===== PAGE {i+1} =====\n\n")
                f.write(text)
    print(f"Done. Extracted {len(pdf.pages)} pages.")
