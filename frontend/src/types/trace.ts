// 追溯相关类型定义

export interface TraceResult {
  chunk_id: string
  source_file: string
  paragraph_location: string
  heading: string
  clause_range: string
  chunk_text: string
  section_heading: string
  section_content: string
  sentence_highlights?: number[]    // 需要高亮的句子索引（1-based）
}
