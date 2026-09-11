"""双源答案交叉校验：study.db 的真题 vs 6wa1t/408-ai-tutor 的 bank.db（MIT）。

两库同源王道但独立转录，答案高度一致说明转录干净；不一致的题输出清单人工裁定。

校验源下载（中文名需 URL 编码）：
  python -c "import urllib.parse; print('https://raw.githubusercontent.com/6wa1t/408-ai-tutor/main/question_banks/%s/bank.db' % urllib.parse.quote('操作系统'))"

用法：python tools/crosscheck_answers.py
"""
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK_DIR = ROOT / "tools" / "vendor" / "crosscheck"
SUBJECTS = ["操作系统", "数据结构", "计算机组成原理", "计算机网络"]


def normalize(text: str) -> str:
    """只留文字/字母/数字并小写（isalnum 对中文同样为 True），消除排版差异"""
    return "".join(ch.lower() for ch in text if ch.isalnum())


def main():
    ours = sqlite3.connect(ROOT / "study.db")
    ours.row_factory = sqlite3.Row
    exam_rows = ours.execute(
        "SELECT id, subject, text, answer, year FROM questions WHERE qtype='exam'"
    ).fetchall()

    # 校验源：规范化题干 -> 答案字母（只要单选且有答案的）
    bank = {}
    for subject in SUBJECTS:
        path = BANK_DIR / f"bank-{subject}.db"
        if not path.exists():
            continue
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        for r in conn.execute("SELECT question_text, answer FROM questions"):
            ans = (r["answer"] or "").strip()
            m = re.match(r"[ABCD]", ans.upper())
            if not m:
                continue
            bank.setdefault(normalize(r["question_text"] or ""), m.group(0))

    matched = agreed = 0
    disagree = []
    unmatched_sample = []
    for row in exam_rows:
        key = normalize(row["text"])
        bank_ans = bank.get(key)
        if bank_ans is None:
            # 容错：取前 30 个规范化字符做前缀匹配
            hits = [v for k, v in bank.items() if k.startswith(key[:30]) and len(key) >= 30]
            bank_ans = hits[0] if len(set(hits)) == 1 else None
        if bank_ans is None:
            if len(unmatched_sample) < 3:
                unmatched_sample.append(row["text"][:40])
            continue
        matched += 1
        if "ABCD"[row["answer"]] == bank_ans:
            agreed += 1
        else:
            disagree.append(
                f"  #{row['id']} [{row['year']}/{row['subject']}] "
                f"我库={'ABCD'[row['answer']]} 校验源={bank_ans} | {row['text'][:50]}"
            )

    print(f"真题 {len(exam_rows)} 题中：匹配到校验源 {matched}，答案一致 {agreed}，"
          f"不一致 {len(disagree)}，未匹配 {len(exam_rows) - matched}")
    if disagree:
        print("不一致清单（人工裁定后直接改 study.db）：")
        print("\n".join(disagree))


if __name__ == "__main__":
    main()
