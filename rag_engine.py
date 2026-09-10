from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_NOTES_ROOT = BASE_DIR / "CSPostgraduate-408" / "408Notes"
DEFAULT_SOURCE_DIRS = ["操作系统", "DataStructure", "计算机组成原理", "计算机网络"]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
FENCE_RE = re.compile(r"^```")
SEPARATOR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_path: str
    subject: str
    title_path: str
    content: str
    tokens: tuple[str, ...]


@dataclass
class SearchResult:
    chunk_id: str
    source_path: str
    subject: str
    title_path: str
    content: str
    score: float


def detect_subject(path: Path) -> str:
    parts = path.parts
    if "408Notes" in parts:
        idx = parts.index("408Notes")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return "未分类"


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = HTML_COMMENT_RE.sub("", text)
    text = re.sub(r"^---\s*$.*?^---\s*$", "", text, flags=re.M | re.S)
    text = IMAGE_RE.sub("", text)
    text = LINK_RE.sub(r"\1", text)
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if SEPARATOR_RE.match(stripped):
            continue
        if stripped in {"-", "*", "_"}:
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def iter_markdown_blocks(text: str) -> Iterable[tuple[str, str]]:
    lines = text.splitlines()
    in_fence = False
    heading_stack: list[str] = []
    buffer: list[str] = []
    blocks: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal buffer
        content = "\n".join(buffer).strip()
        buffer = []
        if content:
            blocks.append(("text", content))

    for line in lines:
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            buffer.append(line)
            continue

        heading_match = HEADING_RE.match(line) if not in_fence else None
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(heading)
            blocks.append(("heading", " / ".join(heading_stack)))
            continue

        if not line.strip() and not in_fence:
            flush()
            continue

        buffer.append(line)

    flush()
    return blocks


def chunk_markdown(text: str, max_chars: int = 900, overlap_chars: int = 120) -> list[str]:
    blocks = iter_markdown_blocks(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def emit() -> None:
        nonlocal current, current_len
        content = "\n".join(current).strip()
        if content:
            chunks.append(content)
        current = []
        current_len = 0

    for kind, block in blocks:
        piece = block.strip()
        if not piece:
            continue
        if kind == "heading":
            if current:
                emit()
            current.append(piece)
            current_len = len(piece)
            continue
        if current_len + len(piece) + 2 > max_chars and current:
            emit()
            if overlap_chars and chunks:
                tail = chunks[-1][-overlap_chars:]
                if tail:
                    current.append(tail)
                    current_len = len(tail)
        current.append(piece)
        current_len += len(piece) + 1

    emit()
    return chunks


def tokenize(text: str) -> list[str]:
    normalized = text.lower()
    tokens: list[str] = []
    for token in TOKEN_RE.findall(normalized):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) == 1:
                tokens.append(token)
            else:
                tokens.extend(token[i : i + 2] for i in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


class RagCorpus:
    def __init__(
        self,
        notes_root: Path = DEFAULT_NOTES_ROOT,
        source_dirs: list[str] | None = None,
    ):
        self.notes_root = notes_root
        self.source_dirs = source_dirs or DEFAULT_SOURCE_DIRS
        self.chunks: list[Chunk] = []
        self.idf: dict[str, float] = {}
        self.avg_len = 0.0
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return

        raw_chunks: list[Chunk] = []
        doc_freq: defaultdict[str, int] = defaultdict(int)
        total_len = 0
        md_files: list[Path] = []

        for source_dir in self.source_dirs:
            base_dir = self.notes_root / source_dir
            if base_dir.exists():
                md_files.extend(sorted(base_dir.rglob("*.md")))

        for md_file in md_files:
            try:
                text = md_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = md_file.read_text(encoding="gbk", errors="ignore")

            clean = normalize_text(text)
            if len(clean) < 20:
                continue

            subject = detect_subject(md_file)
            rel = md_file.relative_to(self.notes_root).as_posix()
            title = rel.rsplit("/", 1)[0] if "/" in rel else rel

            for idx, chunk_text in enumerate(chunk_markdown(clean)):
                tokens = tokenize(chunk_text)
                if not tokens:
                    continue
                chunk = Chunk(
                    chunk_id=f"{rel}::{idx}",
                    source_path=rel,
                    subject=subject,
                    title_path=title,
                    content=chunk_text.strip(),
                    tokens=tuple(tokens),
                )
                raw_chunks.append(chunk)
                total_len += len(tokens)
                for token in set(tokens):
                    doc_freq[token] += 1

        doc_count = max(len(raw_chunks), 1)
        self.idf = {
            token: math.log((doc_count + 1) / (freq + 1)) + 1.0
            for token, freq in doc_freq.items()
        }
        self.avg_len = total_len / doc_count if raw_chunks else 0.0
        self.chunks = raw_chunks
        self._loaded = True

    def stats(self) -> dict[str, object]:
        self.load()
        subject_counts: dict[str, int] = defaultdict(int)
        for chunk in self.chunks:
            subject_counts[chunk.subject] += 1
        return {
            "notes_root": str(self.notes_root),
            "chunk_count": len(self.chunks),
            "subjects": dict(sorted(subject_counts.items())),
            "avg_chunk_tokens": round(self.avg_len, 2),
        }

    def score_chunk(self, query_tokens: list[str], chunk: Chunk) -> float:
        if not query_tokens or not chunk.tokens:
            return 0.0
        query_counts = Counter(query_tokens)
        doc_counts = Counter(chunk.tokens)
        score = 0.0
        doc_len = len(chunk.tokens)
        for token, qtf in query_counts.items():
            if token not in doc_counts:
                continue
            idf = self.idf.get(token, 1.0)
            tf = doc_counts[token]
            bm25_like = (
                (tf * 2.0) / (tf + 1.5 + 0.75 * (doc_len / (self.avg_len or 1.0)))
                if doc_len
                else 0.0
            )
            score += qtf * idf * bm25_like
        return score

    def search(self, query: str, subject: str | None = None, top_k: int = 5) -> list[SearchResult]:
        self.load()
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        results: list[SearchResult] = []
        for chunk in self.chunks:
            if subject and subject != "全部" and chunk.subject != subject:
                continue
            score = self.score_chunk(query_tokens, chunk)
            if score <= 0:
                continue
            if any(token in chunk.content for token in query_tokens):
                score *= 1.05
            results.append(
                SearchResult(
                    chunk_id=chunk.chunk_id,
                    source_path=chunk.source_path,
                    subject=chunk.subject,
                    title_path=chunk.title_path,
                    content=chunk.content,
                    score=round(score, 6),
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]


@lru_cache(maxsize=1)
def get_corpus() -> RagCorpus:
    corpus = RagCorpus()
    corpus.load()
    return corpus


def format_context(results: list[SearchResult], max_chars: int = 4500) -> str:
    pieces: list[str] = []
    total = 0
    for item in results:
        block = f"[{item.subject}] {item.source_path}\n{item.content}".strip()
        if total + len(block) > max_chars and pieces:
            break
        pieces.append(block)
        total += len(block)
    return "\n\n---\n\n".join(pieces)


def build_messages(query: str, context: str) -> list[dict[str, str]]:
    system = (
        "你是一个面向 408 考研复习的答题助手。"
        "只能依据给定资料回答，优先给出简洁结论，再给出必要解释。"
        "如果资料不足，要明确说明不足，不要编造。"
    )
    user = (
        f"问题：{query}\n\n"
        f"资料：\n{context}\n\n"
        "要求：\n"
        "1. 先直接回答。\n"
        "2. 再给出 2-4 条简短理由。\n"
        "3. 如有来源，请在末尾列出文件名。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_openai_compatible_chat(messages: list[dict[str, str]]) -> str | None:
    api_key = os.getenv("RAG_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("RAG_API_BASE") or os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com"
    model = os.getenv("RAG_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError):
        return None


def answer_question(query: str, subject: str | None = None, top_k: int = 5) -> dict[str, object]:
    corpus = get_corpus()
    results = corpus.search(query=query, subject=subject, top_k=top_k)
    context = format_context(results)
    answer = call_openai_compatible_chat(build_messages(query, context))
    if not answer:
        answer = "未配置生成模型，已返回检索结果。"
    return {
        "query": query,
        "subject": subject or "全部",
        "answer": answer,
        "context": context,
        "sources": [
            {
                "chunk_id": item.chunk_id,
                "source_path": item.source_path,
                "subject": item.subject,
                "title_path": item.title_path,
                "score": item.score,
            }
            for item in results
        ],
    }
