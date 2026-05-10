"""
批量并行运行：9 个 PDF 的两种模式（无反思推荐 + 有反思保留）

用法:
  python scripts/run_batch.py                               # 无反思（推荐，Neo4j双写）
  python scripts/run_batch.py --mode both                   # 有反思 + 无反思都跑
  python scripts/run_batch.py --mode reflect                # 只跑有反思（仅JSON）
  python scripts/run_batch.py --mode no-reflect             # 只跑无反思（推荐）
  python scripts/run_batch.py --max-workers 4               # 限制并行文档数
"""
import sys
import os

# 修复 Windows 控制台编码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import threading

from scripts.run_e2e_test import run_pipeline
from loguru import logger


def find_all_pdfs() -> list[str]:
    """扫描 data/raw/ 下所有 PDF 文件"""
    raw_dir = Path(PROJECT_ROOT) / "data" / "raw"
    pdfs = sorted(
        f.name for f in raw_dir.iterdir()
        if f.suffix.lower() == ".pdf" and f.is_file()
    )
    return pdfs


def main():
    parser = argparse.ArgumentParser(
        description="批量并行运行 9 个 PDF 的抽取 Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["reflect", "no-reflect", "both"],
        default="no-reflect",
        help="运行模式：无反思(推荐，Neo4j双写) / reflect(仅JSON) / both(都跑)（默认 no-reflect）",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=16,
        help="文档级并行数（默认 16，视 API 限速调整）",
    )
    args = parser.parse_args()

    pdfs = find_all_pdfs()
    print(f"\n{'=' * 60}")
    print(f"批量并行 Pipeline 启动 — {datetime.now().strftime('%H:%M:%S')}")
    print(f"发现 {len(pdfs)} 个 PDF")
    print(f"文档级并行数: {args.max_workers}")
    print(f"{'=' * 60}\n")

    for i, p in enumerate(pdfs, 1):
        print(f"  [{i}/{len(pdfs)}] {p}")

    modes = []
    if args.mode in ("reflect", "both"):
        modes.append(("有反思(仅JSON)", False))
    if args.mode in ("no-reflect", "both"):
        modes.append(("无反思(Neo4j双写)", True))

    # both 模式：无反思先跑（推荐），有反思后跑（对比）
    if args.mode == "both":
        modes.reverse()

    for mode_label, no_reflect in modes:
        print(f"\n{'=' * 60}")
        print(f"▶ [{mode_label}模式] 并行运行 {len(pdfs)} 个文档...")
        print(f"{'=' * 60}\n")

        lock = threading.Lock()
        success = 0
        fail = 0

        def run_one(pdf_name: str) -> tuple[str, bool]:
            nonlocal success, fail
            try:
                run_pipeline(pdf_name=pdf_name, no_reflect=no_reflect)
                with lock:
                    success += 1
                return pdf_name, True
            except Exception as e:
                with lock:
                    fail += 1
                logger.error(f"[{mode_label}] {pdf_name} 失败: {e}")
                return pdf_name, False

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {
                executor.submit(run_one, pdf): pdf for pdf in pdfs
            }
            for future in as_completed(futures):
                pdf_name, ok = future.result()
                status = "✅ 完成" if ok else "❌ 失败"
                print(f"  [{mode_label}] {pdf_name} — {status}")

        print(f"\n[{mode_label}] 汇总: {success} 成功, {fail} 失败 / {len(pdfs)} 文档")

    print(f"\n{'=' * 60}")
    print(f"全部完成！{datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
