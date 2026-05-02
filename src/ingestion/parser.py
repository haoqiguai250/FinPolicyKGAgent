"""
Stage 1: 文档解析模块
使用 Docling 将 PDF/Word/HTML 文档解析为结构化文本，保留章节层级

Docling 优势：
- 开源，pip install docling 即可
- 支持 PDF、DOCX、PPTX、HTML 等多种格式
- 保留文档层级结构（标题、段落、列表）
- 输出 DoclingDocument 对象，可导出为 Markdown / JSON
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from loguru import logger

from config.settings import settings


@dataclass
class ParsedDocument:
    """解析后的文档结构"""
    source_file: str                           # 原始文件名
    title: str = ""                            # 文档标题
    doc_type: str = ""                         # 文件类型 (pdf/docx/html)
    sections: list[dict] = field(default_factory=list)  # 章节列表
    full_text: str = ""                        # 完整纯文本
    metadata: dict = field(default_factory=dict)        # 元数据

    def save(self, output_path: Optional[Path] = None) -> Path:
        """保存解析结果为 JSON"""
        if output_path is None:
            output_path = settings.PROCESSED_DIR / f"{Path(self.source_file).stem}_parsed.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        logger.info(f"解析结果已保存: {output_path}")
        return output_path


class DoclingParser:
    """基于 Docling 的文档解析器"""

    def __init__(self):
        self._converter = None

    def _get_converter(self):
        """懒加载 Docling 转换器（首次调用时初始化，避免 import 慢）"""
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()
            logger.info("Docling DocumentConverter 初始化完成")
        return self._converter

    def parse(self, file_path: str | Path) -> ParsedDocument:
        """
        解析单个文档

        Args:
            file_path: 文档路径（支持 PDF/DOCX/HTML 等）

        Returns:
            ParsedDocument: 解析后的结构化文档
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.info(f"开始解析文档: {file_path.name}")

        # 使用 Docling 解析
        converter = self._get_converter()
        result = converter.convert(str(file_path))

        # 导出为 Markdown 格式（保留层级）
        markdown_text = result.document.export_to_markdown()

        # 提取章节结构
        sections = self._extract_sections(result)

        parsed = ParsedDocument(
            source_file=file_path.name,
            title=self._extract_title(result, file_path),
            doc_type=file_path.suffix.lstrip("."),
            sections=sections,
            full_text=markdown_text,
            metadata={
                "num_sections": len(sections),
                "char_count": len(markdown_text),
            },
        )

        logger.info(f"文档解析完成: {len(sections)} 个章节, {len(markdown_text)} 字符")
        return parsed

    def _extract_title(self, result, file_path: Path) -> str:
        """从解析结果中提取文档标题"""
        try:
            # Docling 的文档对象可能包含标题信息
            doc = result.document
            if hasattr(doc, "title") and doc.title:
                return doc.title
        except Exception:
            pass
        # 回退：用文件名作为标题
        return file_path.stem

    def _extract_sections(self, result) -> list[dict]:
        """
        从 Docling 解析结果中提取章节层级

        策略：
        1. 优先使用 Docling label 识别（title/section_header 等）
        2. 对于政策 PDF（Docling 通常只标 text），基于条款编号模式识别章节边界
        3. 兜底：全文作为一个 section
        """
        sections = []
        current_section = None

        try:
            # 第一遍：收集所有文本 item
            items = []
            for item, level in result.document.iterate_items():
                label = item.label if hasattr(item, "label") else "text"
                text = item.text if hasattr(item, "text") else ""
                if text and text.strip():
                    items.append({"label": label, "text": text.strip(), "level": level})

            # 检查是否有 Docling 标注的标题
            has_docling_headers = any(
                it["label"] in ("title", "section_header", "header")
                for it in items
            )

            if has_docling_headers:
                # 策略1：使用 Docling label 识别
                for it in items:
                    if it["label"] in ("title", "section_header", "header"):
                        if current_section:
                            sections.append(current_section)
                        current_section = {
                            "heading": it["text"],
                            "level": self._guess_heading_level(it["label"], it["text"]),
                            "content": "",
                        }
                    elif current_section is not None:
                        current_section["content"] += it["text"] + "\n"
                    else:
                        current_section = {
                            "heading": "前言",
                            "level": 0,
                            "content": it["text"] + "\n",
                        }
            else:
                # 策略2：基于条款编号模式识别（政策 PDF 常见情况）
                sections = self._extract_sections_by_clause_patterns(items)

            if has_docling_headers and current_section:
                sections.append(current_section)

        except Exception as e:
            logger.warning(f"章节提取异常，回退为全文模式: {e}")
            markdown = result.document.export_to_markdown()
            sections = [{"heading": "全文", "level": 0, "content": markdown}]

        return sections

    def _extract_sections_by_clause_patterns(self, items: list[dict]) -> list[dict]:
        """
        基于条款编号模式识别章节边界
        适用于 Docling 没有标注标题的政策 PDF

        识别模式：
        - "一、" / "二、" / "三、" → 一级章节
        - "（一）" / "（二）" → 二级章节
        - "第一条" / "第二条" → 条款
        """
        import re

        # 一级标题模式
        level1_pattern = re.compile(r"^[一二三四五六七八九十]+、")
        # 二级标题模式
        level2_pattern = re.compile(r"^[（(][一二三四五六七八九十]+[）)]")
        # 条款模式
        clause_pattern = re.compile(r"^第[一二三四五六七八九十百千]+[条章节款项]")

        sections = []
        current_section = None

        for it in items:
            text = it["text"]

            # 跳过页面导航文字
            if text in ("字号 大 中 小", "打印本页　 关闭窗口"):
                continue

            # 检测标题/条款开头
            is_level1 = level1_pattern.match(text)
            is_level2 = level2_pattern.match(text)
            is_clause = clause_pattern.match(text)

            if is_level1 or is_clause:
                # 新的一级章节
                if current_section:
                    sections.append(current_section)
                heading = text[:30] + ("..." if len(text) > 30 else "")
                current_section = {
                    "heading": heading,
                    "level": 1,
                    "content": text + "\n",
                }
            elif is_level2:
                # 二级章节
                if current_section:
                    sections.append(current_section)
                heading = text[:30] + ("..." if len(text) > 30 else "")
                current_section = {
                    "heading": heading,
                    "level": 2,
                    "content": text + "\n",
                }
            elif current_section is not None:
                current_section["content"] += text + "\n"
            else:
                # 文档开头的引言内容
                current_section = {
                    "heading": "前言（引言）",
                    "level": 0,
                    "content": text + "\n",
                }

        if current_section:
            sections.append(current_section)

        return sections

    @staticmethod
    def _guess_heading_level(label: str, text: str) -> int:
        """根据标签和文本猜测标题层级"""
        if label == "title":
            return 0
        # 中国政策文件常见标题模式
        if text.startswith(("第", "（")):
            return 1  # 第一章 / （一）
        if text.startswith(("一、", "二、", "三、")):
            return 2
        return 1

    def parse_and_save(self, file_path: str | Path) -> ParsedDocument:
        """解析文档并自动保存结果"""
        parsed = self.parse(file_path)
        parsed.save()
        return parsed


# ── 便捷入口 ──
def parse_document(file_path: str | Path) -> ParsedDocument:
    """解析单个文档的快捷函数"""
    parser = DoclingParser()
    return parser.parse_and_save(file_path)


def parse_batch(dir_path: str | Path) -> list[ParsedDocument]:
    """批量解析目录下所有文档"""
    dir_path = Path(dir_path)
    supported = {".pdf", ".docx", ".doc", ".html", ".htm"}
    files = [f for f in dir_path.iterdir() if f.suffix.lower() in supported]

    if not files:
        logger.warning(f"目录下无支持的文档: {dir_path}")
        return []

    logger.info(f"发现 {len(files)} 个文档待解析")
    parser = DoclingParser()
    results = []
    for f in files:
        try:
            parsed = parser.parse_and_save(f)
            results.append(parsed)
        except Exception as e:
            logger.error(f"解析失败 [{f.name}]: {e}")
    return results
