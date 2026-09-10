"""
StudyMate RAG 知识库「选料扫描」脚本
扫描 CSPostgraduate-408/408Notes 下的四个科目目录，
把「真有内容的 markdown 文件」筛出来，排除空壳/导航目录。

原则：
- 只扫描指定原料目录（操作系统、DataStructure、计算机组成原理、计算机网络）
- 统计每个 .md 的非空内容行数
- 小于 min_lines 视为「空壳/几乎没内容」
- 输出一份「可用原料清单」JSON，供后续切块/向量化使用
"""
from pathlib import Path
import json
import sys

BASE = Path(__file__).resolve().parents[1]  # studymate-ai
NOTES = BASE / "CSPostgraduate-408" / "408Notes"

# 原料目录（选择有真实内容、排除空壳的数据结构）
SOURCE_DIRS = ["操作系统", "DataStructure", "计算机组成原理", "计算机网络"]

# 空壳判定阈值：非空行 < MIN_LINES 视为没内容
MIN_LINES = 15


def count_content_lines(filepath: Path) -> int:
    """统计非空行数（去除纯空白行）"""
    count = 0
    try:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except (UnicodeDecodeError, OSError):
        # 有些文件可能是 GBK 或其他编码，尽力容错
        try:
            with open(filepath, encoding="gbk", errors="ignore") as f:
                for line in f:
                    if line.strip():
                        count += 1
        except OSError:
            pass
    return count


def main():
    usable = []   # 可用原料
    empty = []    # 空壳/几乎没内容
    errors = []

    for sub in SOURCE_DIRS:
        sub_dir = NOTES / sub
        if not sub_dir.exists():
            errors.append(f"目录不存在: {sub}")
            continue
        for md in sorted(sub_dir.rglob("*.md")):
            lines = count_content_lines(md)
            rel = md.relative_to(NOTES).as_posix()
            if lines >= MIN_LINES:
                usable.append({"file": rel, "content_lines": lines})
            else:
                empty.append({"file": rel, "content_lines": lines})

    # 输出可读报告
    print("=" * 60)
    print(f"知识库选料扫描结果")
    print(f"原料目录: {', '.join(SOURCE_DIRS)}")
    print(f"空壳阈值: 非空行 < {MIN_LINES}")
    print("=" * 60)
    print(f"\n✅ 可用原料: {len(usable)} 个文件 (总计内容行 {sum(u['content_lines'] for u in usable)})")
    for u in sorted(usable, key=lambda x: -x["content_lines"])[:15]:
        print(f"   {u['content_lines']:>4} 行  {u['file']}")
    if len(usable) > 15:
        print(f"   ... 以及其他 {len(usable)-15} 个")
    print(f"\n❌ 空壳/不足: {len(empty)} 个文件")
    for e in empty[:8]:
        print(f"   {e['content_lines']:>4} 行  {e['file']}")
    if errors:
        print(f"\n⚠️ 错误: {len(errors)}")
        for er in errors:
            print(f"   - {er}")

    # 保存清单供后续使用
    out = {
        "base": str(NOTES),
        "min_lines": MIN_LINES,
        "usable": usable,
        "empty": empty,
        "total_usable": len(usable),
    }
    out_path = BASE / "tools" / "kb_scan_result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📄 清单已保存: {out_path}")


if __name__ == "__main__":
    main()