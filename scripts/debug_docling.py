"""Debug: 查看 Docling 解析结果的详细结构"""
from docling.document_converter import DocumentConverter, FormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline

# 使用 PyPdfium2 后端（docling_parse 在 Windows 上有路径拼接 bug）
pipeline_options = PdfPipelineOptions()
converter = DocumentConverter(
    allowed_formats=[InputFormat.PDF],
    format_options={
        InputFormat.PDF: FormatOption(
            pipeline_options=pipeline_options,
            backend=PyPdfiumDocumentBackend,
            pipeline_cls=StandardPdfPipeline,
        ),
    },
)
result = converter.convert("data/raw/深圳市有力有效支持发展瞪羚企业、独角兽企业行动计划（2025—2027年）.pdf")
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
