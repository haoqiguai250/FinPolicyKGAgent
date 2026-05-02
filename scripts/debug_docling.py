"""Debug: 查看 Docling 解析结果的详细结构"""
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("data/raw/中国人民银行公告〔2026〕第10号.pdf")
doc = result.document

print("=== Docling iterate_items ===")
for i, (item, level) in enumerate(doc.iterate_items()):
    label = getattr(item, "label", "?")
    text = getattr(item, "text", "?")[:120]
    print(f"  [{i}] level={level} label={label} | {text}")
    if i > 30:
        print("  ... (truncated)")
        break

print("\n=== Markdown Output (first 500 chars) ===")
md = doc.export_to_markdown()
print(md[:500])

print("\n=== Doc body children ===")
body = doc.body
print(f"Body type: {type(body)}")
children = getattr(body, "children", [])
print(f"Body children count: {len(children)}")
for c in children[:10]:
    print(f"  {c}")
