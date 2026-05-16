"""
低空经济政策爬虫引擎（API 搜索模式）
通过深圳政策文件库 API 搜索政策 → 提取详情页 → 下载 PDF

工作流程：
1. 遍历每个搜索任务的关键词
2. 调用 API 获取匹配的政策条目（JSON）
3. 去重检查（URL + 标题）
4. 进入详情页，提取 PDF 附件链接
5. 下载 PDF 到 data/raw/

依赖: curl_cffi（解决 Python 3.13 + OpenSSL 3.x 与 *.gov.cn 的 SSL 兼容性问题）
"""

import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from curl_cffi import requests as cf_requests
from loguru import logger

from config.settings import settings
from src.ingestion.crawler.policy_source import (
    ApiSearchConfig,
    API_BASE_URL,
    API_PAGE_SIZE,
    get_keywords,
    KEYWORDS,
)
from src.ingestion.crawler.dedup import DedupManager


class PolicyCrawlResult:
    """单条政策爬取结果"""

    def __init__(
        self,
        title: str,
        detail_url: str,
        source_name: str,
        department: str,
        publish_date: str = "",
        pdf_url: str = "",
        pdf_path: str = "",
        status: str = "pending",  # pending / downloaded / skipped / failed
        reason: str = "",
    ):
        self.title = title
        self.detail_url = detail_url
        self.source_name = source_name
        self.department = department
        self.publish_date = publish_date
        self.pdf_url = pdf_url
        self.pdf_path = pdf_path
        self.status = status
        self.reason = reason

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "detail_url": self.detail_url,
            "source_name": self.source_name,
            "department": self.department,
            "publish_date": self.publish_date,
            "pdf_url": self.pdf_url,
            "pdf_path": self.pdf_path,
            "status": self.status,
            "reason": self.reason,
        }


class PolicyCrawler:
    """政策爬虫（API 搜索模式）"""

    # 请求配置
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://zcwjk.xxgk.sz.gov.cn:9091/",
    }
    REQUEST_TIMEOUT = 30       # 请求超时（秒）
    REQUEST_DELAY = 1.5        # 请求间隔（秒）
    MAX_RETRIES = 3            # 最大重试次数
    MAX_API_PAGES = 10         # 每个关键词最多翻几页 API

    # PDF 附件链接匹配模式
    PDF_PATTERNS = [
        re.compile(r"\.pdf$", re.IGNORECASE),
        re.compile(r"download.*\.pdf", re.IGNORECASE),
        re.compile(r"attachment.*\.pdf", re.IGNORECASE),
        re.compile(r"/file/.*\.pdf", re.IGNORECASE),
    ]

    def __init__(
        self,
        dedup_manager: DedupManager | None = None,
        keyword_layers: list[str] | None = None,
        max_api_pages: int = 10,
        request_delay: float = 1.5,
    ):
        """
        Args:
            dedup_manager: 去重管理器
            keyword_layers: 使用哪些关键词层，默认 ["core", "industry"]
            max_api_pages: 每个关键词最多翻几页 API
            request_delay: 请求间隔秒数
        """
        self.dedup = dedup_manager or DedupManager()
        self.keywords = get_keywords(keyword_layers or ["core", "industry"])
        self.max_api_pages = max_api_pages
        self.request_delay = request_delay

        # 测试模式：限制最多下载 PDF 数（0 = 不限制）
        self._max_pdfs: int = 0
        self._pdf_download_count: int = 0

        # curl_cffi Session：模拟 Chrome 浏览器，绕过 SSL 兼容性问题
        self.session = cf_requests.Session(impersonate="chrome")
        self.session.headers.update(self.DEFAULT_HEADERS)

        logger.info(f"PolicyCrawler 初始化 (API 模式): {len(self.keywords)} 个关键词, 最多翻 {max_api_pages} 页 API")

    # ── 核心流程 ──

    def crawl_source(self, source: ApiSearchConfig) -> list[PolicyCrawlResult]:
        """
        执行单个搜索任务

        Args:
            source: API 搜索配置

        Returns:
            爬取结果列表
        """
        if not source.enabled:
            logger.info(f"跳过已禁用的搜索任务: {source.name}")
            return []

        logger.info(f"开始搜索: {source.name} ({source.level}), 关键词: {source.search_keywords}")
        all_results = []

        for keyword in source.search_keywords:
            try:
                results = self._search_keyword(source, keyword)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"搜索关键词失败 [{source.name}] '{keyword}': {e}")

            # 关键词之间加间隔
            time.sleep(self.request_delay)

        logger.info(f"完成搜索: {source.name}, 共 {len(all_results)} 条结果")
        return all_results

    def crawl_all(self, sources: list[ApiSearchConfig], max_pdfs: int = 0) -> list[PolicyCrawlResult]:
        """
        执行所有搜索任务

        Args:
            sources: 搜索任务列表
            max_pdfs: 测试用，最多下载几个 PDF（0 = 不限制）

        Returns:
            所有爬取结果
        """
        self._max_pdfs = max_pdfs
        self._pdf_download_count = 0

        if max_pdfs > 0:
            logger.info(f"[测试模式] 限制最多下载 {max_pdfs} 个 PDF")

        all_results = []
        for source in sources:
            # 检查是否已达到 PDF 下载上限
            if max_pdfs > 0 and self._pdf_download_count >= max_pdfs:
                logger.info(f"[测试模式] 已达到 PDF 下载上限 ({max_pdfs})，跳过剩余任务")
                break
            results = self.crawl_source(source)
            all_results.extend(results)
            # 任务之间加间隔
            time.sleep(self.request_delay)

        return all_results

    # ── API 搜索 ──

    def _search_keyword(
        self,
        source: ApiSearchConfig,
        keyword: str,
    ) -> list[PolicyCrawlResult]:
        """
        用单个关键词搜索 API，遍历分页

        Args:
            source: 搜索配置（包含层级筛选）
            keyword: 搜索关键词

        Returns:
            爬取结果列表
        """
        results = []
        seen_titles = set()  # 同一关键词下的标题去重

        for page in range(1, self.max_api_pages + 1):
            logger.info(f"  搜索 '{keyword}' 第 {page}/{self.max_api_pages} 页")

            api_response = self._call_api(keyword, page, source)
            if not api_response:
                break

            data = api_response.get("data", {})
            total = data.get("total", 0)
            records = data.get("records", [])

            if not records:
                logger.info(f"  第 {page} 页无记录，停止翻页")
                break

            logger.info(f"  第 {page} 页: {len(records)} 条记录 (总计 {total})")

            for record in records:
                title = record.get("title", "").strip()
                detail_url = record.get("url", "").strip()
                publish_time_ts = record.get("publishTime", 0)
                department = record.get("publishDept", "") or source.name

                if not title or not detail_url:
                    continue

                # 同关键词内标题去重
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # URL 去重
                if self.dedup.is_url_downloaded(detail_url):
                    continue

                # 标题去重
                if self.dedup.is_title_exists(title):
                    continue

                # 转换发布时间
                publish_date = self._format_timestamp(publish_time_ts)

                logger.info(f"  匹配到政策: {title}")

                # 构建结果
                result = PolicyCrawlResult(
                    title=title,
                    detail_url=detail_url,
                    source_name=source.name,
                    department=department,
                    publish_date=publish_date,
                )

                # 检查下载上限（测试模式）
                if self._max_pdfs > 0 and self._pdf_download_count >= self._max_pdfs:
                    result.status = "skipped"
                    result.reason = f"测试模式：已达下载上限 ({self._max_pdfs})"
                    results.append(result)
                    continue

                # 进入详情页提取 PDF
                pdf_url = self._extract_pdf_from_detail(detail_url)
                if pdf_url:
                    result.pdf_url = pdf_url
                    result.status = "pending"

                    # 下载 PDF
                    pdf_path = self._download_pdf(pdf_url, title=title)
                    if pdf_path:
                        result.pdf_path = str(pdf_path)
                        result.status = "downloaded"
                        self._pdf_download_count += 1  # 测试模式：计数

                        # 内容去重
                        if self.dedup.is_content_exists(pdf_path):
                            result.status = "skipped"
                            result.reason = "内容重复"
                            pdf_path.unlink(missing_ok=True)
                        else:
                            # 记录下载
                            self.dedup.record_download(
                                url=detail_url,
                                title=title,
                                filepath=str(pdf_path.relative_to(settings.DATA_DIR / "raw")),
                                file_path_for_md5=pdf_path,
                            )
                    else:
                        result.status = "failed"
                        result.reason = "PDF 下载失败"
                else:
                    result.status = "skipped"
                    result.reason = "详情页无 PDF 附件"

                results.append(result)

            # 如果当前页已是最后一页，停止
            total_pages = (total + API_PAGE_SIZE - 1) // API_PAGE_SIZE
            if page >= total_pages:
                logger.info(f"  已到最后一页 ({total_pages})，停止翻页")
                break

            # 翻页间隔
            time.sleep(self.request_delay)

        return results

    def _call_api(
        self,
        keyword: str,
        page: int = 1,
        source: ApiSearchConfig | None = None,
    ) -> dict | None:
        """
        调用深圳政策文件库 API

        Args:
            keyword: 搜索关键词
            page: 页码（从 1 开始）
            source: 搜索配置（用于层级筛选）

        Returns:
            API 返回的 JSON 数据，失败返回 None
        """
        params = {
            "pageNumber": page,
            "pageSize": API_PAGE_SIZE,
            "searchContent": keyword,
            "excludeWords": "",
            "policyTheme": source.policy_theme if source else "",
            "policyCat": source.policy_cat if source else "",
            "publishTime": "",
            "country": source.country if source else "",
            "province": source.province if source else "",
            "city": source.city if source else "",
            "area": source.area if source else "",
            "themeCategory": "",
            "industryCategory": "",
            "lifeLabel": "",
            "ageLabel": "",
            "educateLabel": "",
            "censusLabel": "",
            "communeLabel": "",
            "enterpriseStageLabel": "",
            "enterpriseScaleLabel": "",
            "industryLabel": "",
            "timely": "",
            "sort": "",
        }

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    API_BASE_URL,
                    params=params,
                    timeout=self.REQUEST_TIMEOUT,
                )
                response.raise_for_status()

                data = response.json()
                # API 正常返回格式: { "data": { "total": N, "pages": N, "records": [...] } }
                if "data" not in data:
                    logger.warning(f"API 返回异常（无 data 字段）: {list(data.keys())}")
                    return None

                return data

            except Exception as e:
                logger.warning(f"API 请求失败 (attempt {attempt}/{self.MAX_RETRIES}): '{keyword}' - {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.request_delay * attempt)

        return None

    # ── 详情页 PDF 提取 ──

    def _extract_pdf_from_detail(self, detail_url: str) -> str | None:
        """从详情页提取 PDF 附件链接"""
        try:
            response = self._request_get(detail_url)
            if not response:
                return None

            html = response.text

            # 策略1：找 <a> 标签中 href 指向 PDF 的
            pdf_urls = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', html, re.IGNORECASE)
            if pdf_urls:
                return self._resolve_url(detail_url, pdf_urls[0])

            # 策略2：找 iframe / embed 指向 PDF 的
            iframe_urls = re.findall(r'<(?:iframe|embed)[^>]+src=["\']([^"\']*\.pdf[^"\']*)["\']', html, re.IGNORECASE)
            if iframe_urls:
                return self._resolve_url(detail_url, iframe_urls[0])

            # 策略3：找页面中所有含 .pdf 的 URL（宽松匹配）
            all_pdf = re.findall(r'(https?://[^\s"\'<>]+\.pdf[^\s"\'<>]*)', html, re.IGNORECASE)
            if all_pdf:
                return all_pdf[0]

            return None

        except Exception as e:
            logger.warning(f"提取 PDF 链接失败: {detail_url} - {e}")
            return None

    # ── 下载 ──

    def _download_pdf(self, pdf_url: str, title: str = "") -> Path | None:
        """下载 PDF 文件到 data/raw/"""
        try:
            # curl_cffi 不用 stream=True，直接读完整 content
            response = self.session.get(
                pdf_url,
                timeout=self.REQUEST_TIMEOUT * 2,
            )
            response.raise_for_status()

            content = response.content
            content_type = response.headers.get("Content-Type", "")

            # 验证是 PDF
            if "pdf" not in content_type.lower() and not pdf_url.lower().endswith(".pdf"):
                if not content[:5] == b"%PDF-":
                    logger.warning(f"非 PDF 文件，跳过: {pdf_url}")
                    return None

            # 生成文件名（优先用标题）
            filename = self._generate_filename(pdf_url, response, title=title)
            save_path = settings.RAW_DIR / filename

            # 确保目录存在
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            with open(save_path, "wb") as f:
                f.write(content)

            file_size = save_path.stat().st_size
            logger.info(f"  下载完成: {filename} ({file_size / 1024:.1f} KB)")
            return save_path

        except Exception as e:
            logger.error(f"  PDF 下载失败: {pdf_url} - {e}")
            return None

    # ── 通用 HTTP 请求 ──

    def _request_get(self, url: str) -> cf_requests.Response | None:
        """GET 请求（带重试）"""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
                response.raise_for_status()
                return response
            except Exception as e:
                logger.warning(f"请求失败 (attempt {attempt}/{self.MAX_RETRIES}): {url} - {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.request_delay * attempt)
        return None

    # ── 工具方法 ──

    @staticmethod
    def _format_timestamp(ts: int | float | str) -> str:
        """将 Unix 时间戳转为日期字符串"""
        try:
            ts_int = int(ts) // 1000 if int(ts) > 1e12 else int(ts)
            return datetime.fromtimestamp(ts_int).strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError):
            return ""

    @staticmethod
    def _resolve_url(base_url: str, relative_url: str) -> str:
        """解析相对 URL 为绝对 URL"""
        if relative_url.startswith("http"):
            return relative_url
        return urljoin(base_url, relative_url)

    @staticmethod
    def _generate_filename(url: str, response, title: str = "") -> str:
        """生成安全的文件名，优先用政策标题"""
        name = ""

        # 优先用标题
        if title:
            # 去掉常见标题后缀，如"的通知"、"的公告"
            clean_title = re.sub(r"(的通知|的公告|的批复|的意见|的办法|的规定|的函|的答复)$", "", title.strip())
            # 清理非法字符
            name = re.sub(r'[<>:"/\\|?*\s]', "_", clean_title)
            # 去掉连续下划线
            name = re.sub(r'_+', '_', name).strip('_')
            # 限制长度
            if len(name) > 80:
                name = name[:80]

        # 标题为空时，从 URL 或 Content-Disposition 提取
        if not name:
            parsed = urlparse(url)
            path = Path(parsed.path)
            if path.suffix.lower() == ".pdf" and path.name and path.stem not in ("", "download"):
                name = path.stem
            else:
                cd = response.headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    name = cd.split("filename=")[-1].strip('"').strip("'")
                    name = Path(name).stem
                else:
                    import hashlib
                    name = hashlib.md5(url.encode()).hexdigest()[:12]

        # 最终清理
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", name)
        if len(safe_name) > 100:
            safe_name = safe_name[:100]

        return f"{safe_name}.pdf"
