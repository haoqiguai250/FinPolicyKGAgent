"""
Stage 2: 章节感知文本分割模块
按文档逻辑边界（章节/条款）拆分，保持段落主题连贯性

分割规则：
- 主依据：章节标题、条款编号（"第三条"、"（一）"等）
- 辅依据：单节过长时按句号/分号进一步切分
- 长度约束：每个 chunk 500-2560 tokens
- 过短段落与相邻段落合并

每个 chunk 绑定元数据：原文位置、时间戳、来源、政策文号
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from loguru import logger

from config.settings import settings
from src.ingestion.parser import ParsedDocument


@dataclass
class Chunk:
    """单个文本分块"""
    chunk_id: str                              # 唯一 ID（如 chunk_001）
    text: str                                  # 文本内容
    heading: str = ""                          # 所属章节标题
    chapter_idx: int = 0                       # 章节序号
    section_idx: int = 0                       # 段落序号
    token_count: int = 0                       # 估算 token 数
    metadata: dict = field(default_factory=dict)  # 额外元数据

    def estimate_tokens(self) -> int:
        """粗估 token 数（中文约 1.5 字/token）"""
        self.token_count = max(1, int(len(self.text) / 1.5))
        return self.token_count


@dataclass
class ChunkedDocument:
    """分块后的文档"""
    source_file: str
    policy_id: str = ""                        # 政策文号
    publish_date: str = ""                     # 发布日期
    source_url: str = ""                       # 来源 URL
    chunks: list[Chunk] = field(default_factory=list)

    def save(self, output_path: Optional[Path] = None) -> Path:
        """保存分块结果"""
        if output_path is None:
            output_path = settings.PROCESSED_DIR / f"{Path(self.source_file).stem}_chunked.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        logger.info(f"分块结果已保存: {output_path} ({len(self.chunks)} 个 chunks)")
        return output_path


# 中国政策文本常见条款编号模式
CLAUSE_PATTERNS = [
    re.compile(r"^第[一二三四五六七八九十百千]+[条章节款项]"),   # 第一条、第三章
    re.compile(r"^[（(][一二三四五六七八九十]+[）)]"),           # （一）、(二)
    re.compile(r"^\d+[、.]"),                                   # 1、2.
    re.compile(r"^[一二三四五六七八九十]+、"),                   # 一、二、
]

# 提取条款编号的模式（用于溯源定位）
CLAUSE_EXTRACT_PATTERNS = [
    re.compile(r"第([一二三四五六七八九十百千]+)条"),
    re.compile(r"第([一二三四五六七八九十百千]+)章"),
    re.compile(r"[（(]([一二三四五六七八九十]+)[）)]"),
    re.compile(r"(\d+)[、.]"),
    re.compile(r"([一二三四五六七八九十]+)、"),
]


class SectionAwareChunker:
    """章节感知文本分割器"""

    # 分块参数（2.5x，减少 chunk 数量降低 LLM 调用次数）
    MIN_TOKENS = 200       # 过短则合并（绝对阈值，防垃圾 chunk，不需随 MAX 缩放）
    TARGET_TOKENS = 1500   # 目标长度
    MAX_TOKENS = 2560      # 超过则拆分

    def chunk(self, parsed_doc: ParsedDocument) -> ChunkedDocument:
        """
        对解析后的文档进行章节感知分块

        Args:
            parsed_doc: Docling 解析后的文档

        Returns:
            ChunkedDocument: 分块结果
        """
        logger.info(f"开始分块: {parsed_doc.source_file} ({len(parsed_doc.sections)} 章节)")

        chunks = []
        chunk_counter = 0

        for chapter_idx, section in enumerate(parsed_doc.sections):
            heading = section.get("heading", "")
            content = section.get("content", "").strip()
            level = section.get("level", 0)

            if not content:
                continue

            # 尝试按条款边界进一步拆分
            sub_sections = self._split_by_clauses(content)

            for section_idx, sub_text in enumerate(sub_sections):
                sub_text = sub_text.strip()
                if not sub_text:
                    continue

                # 估算 tokens
                est_tokens = max(1, int(len(sub_text) / 1.5))

                # 过短段落：与上一个 chunk 合并
                if est_tokens < self.MIN_TOKENS and chunks and chunks[-1].heading == heading:
                    chunks[-1].text += "\n" + sub_text
                    chunks[-1].estimate_tokens()
                    # 更新段落定位（合并后条款范围可能扩大）
                    merged_clause = self._extract_clause_range(chunks[-1].text)
                    chunks[-1].metadata["paragraph_location"] = self._build_paragraph_location(heading, merged_clause)
                    continue

                chunk_counter += 1
                clause_range = self._extract_clause_range(sub_text)
                paragraph_location = self._build_paragraph_location(heading, clause_range)
                chunk = Chunk(
                    chunk_id=f"chunk_{chunk_counter:03d}",
                    text=sub_text,
                    heading=heading,
                    chapter_idx=chapter_idx,
                    section_idx=section_idx,
                    metadata={"level": level, "paragraph_location": paragraph_location},
                )
                chunk.estimate_tokens()

                # 过长段落：按句子进一步切分
                if chunk.token_count > self.MAX_TOKENS:
                    sub_chunks = self._split_long_chunk(chunk)
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(chunk)

        result = ChunkedDocument(
            source_file=parsed_doc.source_file,
            policy_id=self._extract_policy_id(parsed_doc.full_text),
            publish_date=self._extract_publish_date(parsed_doc.full_text),
            chunks=chunks,
        )

        logger.info(f"分块完成: {len(chunks)} 个 chunks")
        return result

    @staticmethod
    def _extract_clause_range(text: str) -> str:
        """
        从 chunk 文本中提取条款号范围，生成人类可读的段落定位

        Returns:
            如 "第一条~第四条" / "（一）~（三）" / "" (无法识别时)
        """
        # 优先匹配"第X条"（政策文本最常见的条款编号）
        articles = re.findall(r"第([一二三四五六七八九十百千]+)条", text)
        if articles:
            if articles[0] == articles[-1]:
                return f"第{articles[0]}条"
            return f"第{articles[0]}条~第{articles[-1]}条"

        # 其次匹配"第X章"
        chapters = re.findall(r"第([一二三四五六七八九十百千]+)章", text)
        if chapters:
            if chapters[0] == chapters[-1]:
                return f"第{chapters[0]}章"
            return f"第{chapters[0]}章~第{chapters[-1]}章"

        # 再匹配"（一）"形式
        items_cn = re.findall(r"[（(]([一二三四五六七八九十]+)[）)]", text)
        if items_cn:
            if items_cn[0] == items_cn[-1]:
                return f"（{items_cn[0]}）"
            return f"（{items_cn[0]}）~（{items_cn[-1]}）"

        # 匹配数字编号 "1." / "1、"
        items_num = re.findall(r"(?<![第])((?<!\d)\d+)[、.]", text)
        if items_num:
            if items_num[0] == items_num[-1]:
                return f"第{items_num[0]}项"
            return f"第{items_num[0]}项~第{items_num[-1]}项"

        # 匹配"一、"形式
        items_dash = re.findall(r"^([一二三四五六七八九十]+)、", text, re.MULTILINE)
        if items_dash:
            if items_dash[0] == items_dash[-1]:
                return f"{items_dash[0]}、"
            return f"{items_dash[0]}、~{items_dash[-1]}、"

        return ""

    @staticmethod
    def _build_paragraph_location(heading: str, clause_range: str) -> str:
        """
        组合章节标题和条款范围，生成完整的段落定位

        Returns:
            如 "第一章优化产业空间配置 第一条~第四条"
            或  "第一章优化产业空间配置" (无条款号时)
        """
        if clause_range:
            return f"{heading} {clause_range}"
        return heading

    def _split_by_clauses(self, text: str) -> list[str]:
        """按条款边界拆分文本"""
        lines = text.split("\n")
        sections = []
        current = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # 检查是否是条款开头
            is_clause_start = any(p.match(line_stripped) for p in CLAUSE_PATTERNS)

            if is_clause_start and current:
                sections.append("\n".join(current))
                current = [line_stripped]
            else:
                current.append(line_stripped)

        if current:
            sections.append("\n".join(current))

        return sections if sections else [text]

    def _split_long_chunk(self, chunk: Chunk) -> list[Chunk]:
        """将过长的 chunk 按句子切分"""
        sentences = re.split(r"[。；！？\n]", chunk.text)
        sentences = [s.strip() for s in sentences if s.strip()]

        sub_chunks = []
        current_text = ""
        counter = 0

        for sent in sentences:
            candidate = current_text + "。" + sent if current_text else sent
            est = max(1, int(len(candidate) / 1.5))

            if est > self.MAX_TOKENS and current_text:
                counter += 1
                sub_clause = self._extract_clause_range(current_text)
                sub_location = self._build_paragraph_location(chunk.heading, sub_clause)
                sub = Chunk(
                    chunk_id=f"{chunk.chunk_id}_sub{counter}",
                    text=current_text,
                    heading=chunk.heading,
                    chapter_idx=chunk.chapter_idx,
                    section_idx=chunk.section_idx,
                    metadata={**chunk.metadata, "is_sub_chunk": True, "paragraph_location": sub_location},
                )
                sub.estimate_tokens()
                sub_chunks.append(sub)
                current_text = sent
            else:
                current_text = candidate

        if current_text:
            counter += 1
            sub_clause = self._extract_clause_range(current_text)
            sub_location = self._build_paragraph_location(chunk.heading, sub_clause)
            sub = Chunk(
                chunk_id=f"{chunk.chunk_id}_sub{counter}",
                text=current_text,
                heading=chunk.heading,
                chapter_idx=chunk.chapter_idx,
                section_idx=chunk.section_idx,
                metadata={**chunk.metadata, "is_sub_chunk": True, "paragraph_location": sub_location},
            )
            sub.estimate_tokens()
            sub_chunks.append(sub)

        return sub_chunks

    @staticmethod
    def _extract_policy_id(text: str) -> str:
        """从文本中提取政策文号，如 银发〔2025〕123号"""
        patterns = [
            r"[^\s]{2,4}〔\d{4}〕\d+号",
            r"[^\s]{2,4}\[\d{4}\]\d+号",
            r"[^\s]{2,4}第\d+号",
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                return match.group()
        return ""

    @staticmethod
    def _extract_publish_date(text: str) -> str:
        """从文本中提取发布日期"""
        patterns = [
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            r"(\d{4})-(\d{1,2})-(\d{1,2})",
        ]
        for p in patterns:
            match = re.search(p, text)
            if match:
                y, m, d = match.group(1), match.group(2), match.group(3)
                return f"{y}-{int(m):02d}-{int(d):02d}"
        return ""


# ── 便捷入口 ──
def chunk_document(parsed_doc: ParsedDocument) -> ChunkedDocument:
    """分块快捷函数"""
    chunker = SectionAwareChunker()
    result = chunker.chunk(parsed_doc)
    result.save()
    return result
