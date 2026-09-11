from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from rag_engine import answer_question, get_corpus


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "study.db"


QUESTIONS = [
    {
        "subject": "数据结构",
        "text": "二叉树的层序遍历通常需要借助哪种数据结构？",
        "options": ["栈", "队列", "数组", "哈希表"],
        "answer": 1,
        "analysis": "层序遍历按层访问结点，通常使用队列辅助实现。",
    },
    {
        "subject": "数据结构",
        "text": "下列排序算法中，平均时间复杂度为 O(n log n) 的是？",
        "options": ["直接插入排序", "归并排序", "冒泡排序", "简单选择排序"],
        "answer": 1,
        "analysis": "归并排序采用分治策略，平均时间复杂度为 O(n log n)。",
    },
    {
        "subject": "数据结构",
        "text": "哈希表中发生冲突时，下列哪种处理方法属于开放定址法？",
        "options": ["拉链法", "线性探测再散列", "建立公共溢出区", "二叉排序树法"],
        "answer": 1,
        "analysis": "线性探测再散列是典型的开放定址法。",
    },
    {
        "subject": "组成原理",
        "text": "补码表示的一个核心优点是？",
        "options": ["只能表示正数", "减法可以转换为加法", "无法表示零", "必须使用十进制电路"],
        "answer": 1,
        "analysis": "补码系统下减法可转化为加法统一处理。",
    },
    {
        "subject": "组成原理",
        "text": "DMA 方式适合用于？",
        "options": ["CPU 与寄存器之间的单字传输", "高速外设与主存之间的大批量数据传输", "仅用于程序控制方式无效的场景", "只能传输指令，不能传输数据"],
        "answer": 1,
        "analysis": "DMA 适合高速、大批量数据在外设与主存之间传输。",
    },
    {
        "subject": "组成原理",
        "text": "关于中断响应过程，下列说法正确的是：",
        "options": [
            "CPU 响应中断后先执行中断服务程序，再保存现场",
            "CPU 响应中断后通常先保存现场，再转入中断服务程序",
            "中断响应过程中 CPU 不需要识别中断源",
            "中断处理完成后不需要恢复现场",
        ],
        "answer": 1,
        "analysis": "CPU 响应中断后，一般先保护现场，再转入中断服务程序。",
    },
    {
        "subject": "操作系统",
        "text": "在页面置换算法中，最容易产生 Belady 异常的是？",
        "options": ["FIFO", "LRU", "OPT", "CLOCK"],
        "answer": 0,
        "analysis": "FIFO 可能出现分配更多物理块反而缺页次数增加的 Belady 异常。",
    },
    {
        "subject": "操作系统",
        "text": "死锁产生的四个必要条件中，不包括下面哪一项？",
        "options": ["互斥条件", "请求与保持条件", "资源可共享条件", "循环等待条件"],
        "answer": 2,
        "analysis": "资源可共享不是死锁条件，反而与互斥相反。",
    },
    {
        "subject": "操作系统",
        "text": "下列文件分配方式中，既支持随机访问又便于文件扩展的是？",
        "options": ["连续分配", "链接分配", "索引分配", "顺序分配"],
        "answer": 2,
        "analysis": "索引分配支持随机访问且扩展方便。",
    },
    {
        "subject": "计算机网络",
        "text": "CSMA/CD 协议中，发生碰撞后发送站通常采取的措施是？",
        "options": ["立即停止并永久放弃发送", "立刻重发，不做等待", "执行二进制指数退避后重传", "只接收不发送"],
        "answer": 2,
        "analysis": "发生碰撞后一般先退避，再重传。",
    },
    {
        "subject": "计算机网络",
        "text": "将 192.168.1.0/24 平均划分为 4 个等大小子网后，每个子网的前缀长度是？",
        "options": ["/25", "/26", "/27", "/28"],
        "answer": 1,
        "analysis": "将 /24 划分为 4 个子网需要借 2 位主机位，因此前缀变为 /26。",
    },
    {
        "subject": "计算机网络",
        "text": "TCP 拥塞控制中，慢开始阶段的特点是：",
        "options": ["拥塞窗口线性增长", "拥塞窗口指数增长", "拥塞窗口保持不变", "拥塞窗口随机波动"],
        "answer": 1,
        "analysis": "慢开始阶段 cwnd 每经过一个 RTT 近似翻倍。",
    },
]


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                text TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                answer INTEGER NOT NULL,
                analysis TEXT NOT NULL
            )
            """
        )
        # CREATE TABLE IF NOT EXISTS 不会给已存在的旧表加列，这里手动补（幂等）
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(questions)").fetchall()
        }
        for column_def in ("year INTEGER", "source TEXT", "qtype TEXT DEFAULT 'chapter'"):
            if column_def.split()[0] not in existing_cols:
                conn.execute(f"ALTER TABLE questions ADD COLUMN {column_def}")
        # 老库存量行补默认来源（新种子由下方 INSERT 直接带 source）
        conn.execute(
            "UPDATE questions SET source = '自编入门题' WHERE source IS NULL"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL UNIQUE,
                selected_answer INTEGER NOT NULL,
                is_correct INTEGER NOT NULL,
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(question_id) REFERENCES questions(id)
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        if count == 0:
            conn.executemany(
                """
                INSERT INTO questions (
                    subject, text, option_a, option_b, option_c, option_d,
                    answer, analysis, year, source, qtype
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'chapter')
                """,
                [
                    (
                        question["subject"],
                        question["text"],
                        question["options"][0],
                        question["options"][1],
                        question["options"][2],
                        question["options"][3],
                        question["answer"],
                        question["analysis"],
                        "自编入门题",
                    )
                    for question in QUESTIONS
                ],
            )
        conn.execute(
            """
            DELETE FROM answers
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM answers
                GROUP BY question_id
            )
            """
        )


def row_to_question(row):
    return {
        "id": row["id"],
        "subject": row["subject"],
        "text": row["text"],
        "options": [
            row["option_a"],
            row["option_b"],
            row["option_c"],
            row["option_d"],
        ],
        "answer": row["answer"],
        "analysis": row["analysis"],
        "year": row["year"],
        "source": row["source"],
        "qtype": row["qtype"],
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="StudyMate AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/questions")
def get_questions():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM questions ORDER BY id").fetchall()
    questions = [row_to_question(row) for row in rows]
    return {"count": len(questions), "questions": questions}


@app.get("/api/questions/{subject}")
def get_questions_by_subject(subject: str):
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM questions WHERE subject = ? ORDER BY id",
            (subject,),
        ).fetchall()
    questions = [row_to_question(row) for row in rows]
    return {"subject": subject, "count": len(questions), "questions": questions}


@app.post("/api/submit")
def submit_answer(payload: dict):
    question_id = payload.get("question_id")
    selected_answer = payload.get("selected_answer")

    if not isinstance(question_id, int) or not isinstance(selected_answer, int):
        return {"error": "question_id and selected_answer must be integers"}

    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        if row is None:
            return {"error": "question not found"}

        is_correct = int(selected_answer == row["answer"])
        existing = conn.execute(
            "SELECT id FROM answers WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO answers (question_id, selected_answer, is_correct)
                VALUES (?, ?, ?)
                """,
                (question_id, selected_answer, is_correct),
            )
        else:
            conn.execute(
                """
                UPDATE answers
                SET selected_answer = ?, is_correct = ?, answered_at = CURRENT_TIMESTAMP
                WHERE question_id = ?
                """,
                (selected_answer, is_correct, question_id),
            )

    return {
        "correct": bool(is_correct),
        "correct_answer": row["answer"],
        "analysis": row["analysis"],
    }


@app.get("/api/stats")
def get_stats():
    with get_db_connection() as conn:
        total_answers = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
        correct_answers = conn.execute(
            "SELECT COUNT(*) FROM answers WHERE is_correct = 1"
        ).fetchone()[0]

        subject_rows = conn.execute(
            """
            SELECT
                q.subject AS subject,
                COUNT(a.id) AS total_answers,
                SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) AS correct_answers
            FROM answers a
            JOIN questions q ON q.id = a.question_id
            GROUP BY q.subject
            ORDER BY q.subject
            """
        ).fetchall()

    accuracy = round((correct_answers / total_answers * 100) if total_answers else 0, 2)
    subjects = [
        {
            "subject": row["subject"],
            "total_answers": row["total_answers"],
            "correct_answers": row["correct_answers"] or 0,
            "accuracy": round(
                ((row["correct_answers"] or 0) / row["total_answers"] * 100)
                if row["total_answers"]
                else 0,
                2,
            ),
        }
        for row in subject_rows
    ]

    return {
        "total_answers": total_answers,
        "correct_answers": correct_answers,
        "accuracy": accuracy,
        "subjects": subjects,
    }


@app.get("/api/history")
def get_history():
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                a.question_id,
                q.text AS question_text,
                q.subject,
                a.selected_answer,
                q.answer AS correct_answer,
                a.is_correct,
                a.answered_at
            FROM answers a
            JOIN questions q ON q.id = a.question_id
            ORDER BY a.answered_at DESC, a.id DESC
            """
        ).fetchall()

    history = [
        {
            "question_id": row["question_id"],
            "question_text": row["question_text"],
            "subject": row["subject"],
            "selected_answer": row["selected_answer"],
            "correct_answer": row["correct_answer"],
            "is_correct": bool(row["is_correct"]),
            "answered_at": row["answered_at"],
        }
        for row in rows
    ]

    return {"count": len(history), "history": history}





@app.get("/api/rag/status")
def rag_status():
    return get_corpus().stats()


@app.post("/api/rag/search")
def rag_search(payload: dict):
    query = payload.get("query")
    subject = payload.get("subject")
    top_k = payload.get("top_k", 5)

    if not isinstance(query, str) or not query.strip():
        return {"error": "query must be a non-empty string"}
    if subject is not None and not isinstance(subject, str):
        return {"error": "subject must be a string"}
    if not isinstance(top_k, int) or top_k < 1 or top_k > 10:
        return {"error": "top_k must be an integer between 1 and 10"}

    results = get_corpus().search(query=query.strip(), subject=subject, top_k=top_k)
    return {
        "query": query.strip(),
        "subject": subject or "全部",
        "count": len(results),
        "results": [
            {
                "chunk_id": item.chunk_id,
                "source_path": item.source_path,
                "subject": item.subject,
                "title_path": item.title_path,
                "score": item.score,
                "content": item.content,
            }
            for item in results
        ],
    }


@app.post("/api/rag/ask")
def rag_ask(payload: dict):
    query = payload.get("query")
    subject = payload.get("subject")
    top_k = payload.get("top_k", 5)

    if not isinstance(query, str) or not query.strip():
        return {"error": "query must be a non-empty string"}
    if subject is not None and not isinstance(subject, str):
        return {"error": "subject must be a string"}
    if not isinstance(top_k, int) or top_k < 1 or top_k > 10:
        return {"error": "top_k must be an integer between 1 and 10"}

    return answer_question(query=query.strip(), subject=subject, top_k=top_k)

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)



