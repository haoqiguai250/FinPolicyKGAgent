"""
去重模块
三重指纹防止重复下载和入库：
1. URL hash — 同一链接不重复下载
2. 标题 hash — 同一政策在不同栏目转发时不重复
3. 内容 md5 — 同一文件挂在不同 URL 时只存一份

状态文件：data/crawl_state.json
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import settings


class DedupManager:
    """去重管理器"""

    def __init__(self, state_path: Optional[Path] = None):
        self.state_path = state_path or settings.DATA_DIR / "crawl_state.json"
        self._state: dict = self._load_state()

    def _load_state(self) -> dict:
        """加载状态文件"""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                logger.info(f"加载爬取状态: {len(state.get('urls', {}))} URL 记录, {len(state.get('titles', {}))} 标题记录")
                return state
            except Exception as e:
                logger.warning(f"状态文件加载失败，重新创建: {e}")

        return {
            "last_crawl_time": None,
            "urls": {},         # url_hash → {title, download_time, filepath}
            "titles": {},       # title_hash → filepath
            "content_md5": {},  # content_md5 → filepath
        }

    def save_state(self):
        """保存状态文件"""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)
        logger.info(f"爬取状态已保存: {self.state_path}")

    @staticmethod
    def _hash(text: str) -> str:
        """计算文本 hash"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _file_md5(file_path: Path) -> str:
        """计算文件内容 md5"""
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def is_url_downloaded(self, url: str) -> bool:
        """检查 URL 是否已下载"""
        url_hash = self._hash(url)
        return url_hash in self._state["urls"]

    def is_title_exists(self, title: str) -> bool:
        """检查标题是否已存在"""
        title_hash = self._hash(title.strip())
        return title_hash in self._state["titles"]

    def is_content_exists(self, file_path: Path) -> bool:
        """检查文件内容是否已存在"""
        try:
            content_md5 = self._file_md5(file_path)
            return content_md5 in self._state["content_md5"]
        except FileNotFoundError:
            return False

    def is_duplicate(self, url: str, title: str, file_path: Optional[Path] = None) -> bool:
        """
        综合去重检查

        Args:
            url: 下载 URL
            title: 政策标题
            file_path: 已下载的文件路径（用于内容去重）

        Returns:
            True 表示重复，应跳过
        """
        # 第一重：URL 去重
        if self.is_url_downloaded(url):
            logger.debug(f"URL 重复，跳过: {url}")
            return True

        # 第二重：标题去重
        if self.is_title_exists(title):
            logger.debug(f"标题重复，跳过: {title}")
            return True

        # 第三重：内容去重（文件已下载时检查）
        if file_path and file_path.exists():
            if self.is_content_exists(file_path):
                logger.debug(f"内容重复，跳过: {file_path.name}")
                return True

        return False

    def record_download(self, url: str, title: str, filepath: str, file_path_for_md5: Optional[Path] = None):
        """
        记录一次下载

        Args:
            url: 下载 URL
            title: 政策标题
            filepath: 保存路径（相对路径字符串）
            file_path_for_md5: 用于计算内容 md5 的文件路径
        """
        now = datetime.now().isoformat()

        # 记录 URL
        url_hash = self._hash(url)
        self._state["urls"][url_hash] = {
            "title": title,
            "url": url,
            "download_time": now,
            "filepath": filepath,
        }

        # 记录标题
        title_hash = self._hash(title.strip())
        self._state["titles"][title_hash] = filepath

        # 记录内容 md5
        if file_path_for_md5 and file_path_for_md5.exists():
            content_md5 = self._file_md5(file_path_for_md5)
            self._state["content_md5"][content_md5] = filepath

    def update_last_crawl_time(self):
        """更新最后爬取时间"""
        self._state["last_crawl_time"] = datetime.now().isoformat()

    def get_last_crawl_time(self) -> Optional[str]:
        """获取最后爬取时间"""
        return self._state.get("last_crawl_time")

    def get_stats(self) -> dict:
        """获取去重统计"""
        return {
            "total_urls": len(self._state["urls"]),
            "total_titles": len(self._state["titles"]),
            "total_content_md5": len(self._state["content_md5"]),
            "last_crawl_time": self._state.get("last_crawl_time"),
        }
