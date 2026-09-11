"""导入开源 408 题库到 study.db。

数据来源：https://github.com/lij768423-svg/408- 的 data.json（ISC 协议，2386 题）。
该文件放本目录 vendor/ 下（已 gitignore），首次使用自行下载：
  curl -L -o tools/vendor/408-data.json \
    https://raw.githubusercontent.com/lij768423-svg/408-/main/data.json

导入规则：
- 只导 single_choice（现有刷题交互是单选；多选题只统计不导入）
- 跳过题干含图片引用的题（源数据是纯文本，图缺失则题不可答）
- 真题：题干的【XXXX 统考真题】前缀提取为 year 字段并在题干中去除
- 幂等：按 题干+四选项 的指纹去重（重复运行 / 与已有题撞车都不会重复入库）
- 导入前自动备份 study.db

用法：python tools/import_questions.py [--dry-run]
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import backend  # 复用 init_db()，保证与后端同一套建表/迁移逻辑

DATA_PATH = ROOT / "tools" / "vendor" / "408-data.json"
DB_PATH = ROOT / "study.db"

# 数据源科目名 -> 本库科目名（其余一致）
SUBJECT_MAP = {"计算机组成原理": "组成原理"}
EXAM_PAT = re.compile(r"^【(\d{4})\s*统考真题】\s*")
IMG_PAT = re.compile(r"!\[")


def fingerprint(text: str, options: list) -> str:
    return hashlib.md5((text + "|" + "|".join(options)).encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args()

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    backup = DB_PATH.with_name(f"study.db.bak-{datetime.now():%Y%m%d-%H%M%S}")
    if not args.dry_run:
        shutil.copy2(DB_PATH, backup)

    backend.init_db()  # 建表 + 老库迁移（year/source/qtype 列）
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    existing = {
        fingerprint(
            r["text"],
            [r["option_a"], r["option_b"], r["option_c"], r["option_d"]],
        )
        for r in conn.execute(
            "SELECT text, option_a, option_b, option_c, option_d FROM questions"
        )
    }

    rows = []
    skipped = {"multiple_choice": 0, "image_stem": 0, "empty_option": 0, "duplicate": 0}
    for q in data["questions"]:
        if q["type"] != "single_choice":
            skipped["multiple_choice"] += 1
            continue
        text = q["question"].strip()
        if IMG_PAT.search(text):
            skipped["image_stem"] += 1
            continue
        options = [q["options"][k].strip() for k in "ABCD"]
        if not all(options):
            skipped["empty_option"] += 1
            continue

        m = EXAM_PAT.match(text)
        if m:
            year = int(m.group(1))
            source = f"{year}年统考真题"
            qtype = "exam"
            text = EXAM_PAT.sub("", text)
        else:
            year = None
            source = f"王道·{q['book']}·第{q['chapter']}章 {q['chapter_title']}"
            qtype = "chapter"

        fp = fingerprint(text, options)
        if fp in existing:
            skipped["duplicate"] += 1
            continue
        existing.add(fp)

        subject = SUBJECT_MAP.get(q["book"], q["book"])
        rows.append(
            (
                subject,
                text,
                options[0],
                options[1],
                options[2],
                options[3],
                "ABCD".index(q["answer"][0]),
                q["explanation"].strip(),
                year,
                source,
                qtype,
            )
        )

    print(f"源数据 {len(data['questions'])} 题 -> 待导入 {len(rows)} 题，跳过 {skipped}")
    if args.dry_run:
        conn.close()
        return

    conn.executemany(
        """
        INSERT INTO questions (
            subject, text, option_a, option_b, option_c, option_d,
            answer, analysis, year, source, qtype
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    print(f"已备份原库 -> {backup.name}")

    # 导入报告
    total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    print(f"库内总题数: {total}")
    for label, sql in [
        ("按类型", "SELECT qtype, COUNT(*) FROM questions GROUP BY qtype"),
        ("按科目", "SELECT subject, COUNT(*) FROM questions GROUP BY subject"),
        ("真题按年份", "SELECT year, COUNT(*) FROM questions WHERE qtype='exam' GROUP BY year"),
    ]:
        print(label + ":", dict(conn.execute(sql).fetchall()))
    conn.close()


if __name__ == "__main__":
    main()
