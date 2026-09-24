"""One server owns the SQLite database; clients only use the HTTP API."""
import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import normalize_parameters

class Conflict(ValueError):
    pass

class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError("Unsupported database version")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    name TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('reader','editor')));
                CREATE TABLE IF NOT EXISTS samples (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    parent_id TEXT REFERENCES samples(id),
                    created_by TEXT NOT NULL REFERENCES users(name), created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES samples(id),
                    process_type TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    author TEXT NOT NULL REFERENCES users(name), created_at TEXT NOT NULL,
                    submission_id TEXT NOT NULL, request_hash TEXT NOT NULL,
                    supersedes_id TEXT UNIQUE REFERENCES records(id), payload TEXT NOT NULL,
                    UNIQUE(author, submission_id));
                CREATE INDEX IF NOT EXISTS record_timeline ON records(sample_id, occurred_at);
                CREATE INDEX IF NOT EXISTS record_type ON records(process_type, occurred_at);
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL REFERENCES records(id),
                    filename TEXT NOT NULL, size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL, uploaded_by TEXT NOT NULL REFERENCES users(name),
                    uploaded_at TEXT NOT NULL, content BLOB NOT NULL,
                    UNIQUE(record_id, filename, sha256));
                CREATE INDEX IF NOT EXISTS attachment_record ON attachments(record_id);
                PRAGMA user_version=2;
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def add_user(self, name, role):
        token = secrets.token_urlsafe(32)
        with self.connect() as con:
            try:
                con.execute("INSERT INTO users VALUES (?,?,?)", (name, hashlib.sha256(token.encode()).hexdigest(), role))
            except sqlite3.IntegrityError as exc:
                raise Conflict("用户已存在；请使用 rotate-user 更换令牌") from exc
        return token

    def rotate_user(self, name):
        token = secrets.token_urlsafe(32)
        with self.connect() as con:
            changed = con.execute("UPDATE users SET token_hash=? WHERE name=?", (hashlib.sha256(token.encode()).hexdigest(), name)).rowcount
            if not changed:
                raise ValueError("用户不存在")
        return token

    def authenticate(self, token):
        with self.connect() as con:
            row = con.execute("SELECT name, role FROM users WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        return dict(row) if row else None

    def add_sample(self, sample, author):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            parent_kind = {"wafer": "lot", "die": "wafer", "device": "die"}
            if sample.kind == "lot":
                if sample.parent_id is not None:
                    raise ValueError("批次不能指定父级")
            else:
                parent = con.execute("SELECT kind FROM samples WHERE id=?", (sample.parent_id,)).fetchone()
                if not parent or parent["kind"] != parent_kind[sample.kind]:
                    raise ValueError("父级不存在或层级不正确：批次 → 晶圆 → 芯片 → 器件")
            try:
                con.execute("INSERT INTO samples VALUES (?,?,?,?,?)", (sample.id, sample.kind, sample.parent_id, author, self.now()))
            except sqlite3.IntegrityError as exc:
                raise Conflict("样品编号已存在") from exc
        return sample.model_dump()

    def list_samples(self):
        with self.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM samples ORDER BY id")]

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def add_record(self, record, author):
        request = record.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.connect() as con:
            # Serialize the check+insert to make duplicate requests and corrections atomic.
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT * FROM records WHERE author=? AND submission_id=?", (author, record.submission_id)).fetchone()
            if existing:
                if existing["request_hash"] != digest:
                    raise Conflict("相同提交编号对应不同内容，请开始一条新记录")
                return self.decode(existing)
            if not con.execute("SELECT id FROM samples WHERE id=?", (record.sample_id,)).fetchone():
                raise ValueError("请先登记样品编号")
            if record.supersedes_id:
                old = con.execute("SELECT sample_id FROM records WHERE id=?", (record.supersedes_id,)).fetchone()
                if not old or old["sample_id"] != record.sample_id:
                    raise ValueError("更正必须引用同一样品的现有记录")
                if con.execute("SELECT id FROM records WHERE supersedes_id=?", (record.supersedes_id,)).fetchone():
                    raise Conflict("此记录已被更正，请更正最新记录")
            payload = {
                "capture_version": "1.0.0", "equipment_id": record.equipment_id,
                "recipe": record.recipe, "parameters": normalize_parameters(record.parameters),
                "original_parameters": {key: q.model_dump() for key, q in record.parameters.items()},
                "original_occurred_at": record.occurred_at.isoformat(), "notes": record.notes,
            }
            row = ("RUN-" + uuid4().hex, record.sample_id, record.process_type,
                   record.occurred_at.astimezone(timezone.utc).isoformat(), author, self.now(),
                   record.submission_id, digest, record.supersedes_id, json.dumps(payload, ensure_ascii=False))
            con.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)", row)
            saved = con.execute("SELECT * FROM records WHERE id=?", (row[0],)).fetchone()
            return self.decode(saved)

    @staticmethod
    def decode(row):
        result = dict(row)
        result.update(json.loads(result.pop("payload")))
        result.pop("request_hash")
        return result

    def list_records(self, sample_id=None, process_type=None, limit=50, offset=0, include_history=False):
        where, args = [], []
        if not include_history:
            where.append("NOT EXISTS (SELECT 1 FROM records next WHERE next.supersedes_id=records.id)")
        for key, value in (("sample_id", sample_id), ("process_type", process_type)):
            if value:
                where.append(f"{key}=?")
                args.append(value)
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self.connect() as con:
            total = con.execute("SELECT COUNT(*) FROM records" + clause, args).fetchone()[0]
            rows = con.execute("SELECT * FROM records" + clause + " ORDER BY occurred_at DESC, id LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
        return {"total": total, "items": [self.decode(r) for r in rows], "limit": limit, "offset": offset}

    def record_exists(self, record_id):
        with self.connect() as con:
            return con.execute("SELECT 1 FROM records WHERE id=?", (record_id,)).fetchone() is not None

    def add_attachment(self, record_id, filename, content, author):
        # Store original bytes, never extract an archive or execute uploaded data.
        if not filename or len(filename) > 240 or any(ord(c) < 32 or ord(c) == 127 or c in '/\\' for c in filename):
            raise ValueError("文件名无效，请使用不含路径的文件名（不超过240字符）")
        if filename in (".", ".."):
            raise ValueError("文件名无效")
        if not content or len(content) > 50 * 1024 * 1024:
            raise ValueError("文件不能为空，且每个文件不能超过50 MiB")
        digest = hashlib.sha256(content).hexdigest()
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute("SELECT 1 FROM records WHERE id=?", (record_id,)).fetchone():
                raise ValueError("工艺记录不存在")
            old = con.execute("SELECT id FROM attachments WHERE record_id=? AND filename=? AND sha256=?", (record_id, filename, digest)).fetchone()
            if old:
                attachment_id = old["id"]
            else:
                attachment_id = "FILE-" + uuid4().hex
                con.execute("INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?)", (attachment_id, record_id, filename, len(content), digest, author, self.now(), content))
            row = con.execute("SELECT id,record_id,filename,size,sha256,uploaded_by,uploaded_at FROM attachments WHERE id=?", (attachment_id,)).fetchone()
            return dict(row)

    def list_attachments(self, record_id):
        with self.connect() as con:
            # A correction preserves access to attachments on previous revisions.
            rows = con.execute("""
                WITH RECURSIVE lineage(id, supersedes_id) AS (
                    SELECT id, supersedes_id FROM records WHERE id=?
                    UNION ALL
                    SELECT r.id, r.supersedes_id FROM records r JOIN lineage l ON r.id=l.supersedes_id
                )
                SELECT a.id,a.record_id,a.filename,a.size,a.sha256,a.uploaded_by,a.uploaded_at
                FROM attachments a JOIN lineage l ON l.id=a.record_id
                ORDER BY a.uploaded_at,a.id
            """, (record_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_attachment(self, attachment_id):
        with self.connect() as con:
            row = con.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
            return dict(row) if row else None

    def backup(self, destination):
        target = Path(destination).resolve()
        if target == self.path or target.exists():
            raise ValueError("备份路径必须为新的文件，不能覆盖现有文件")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source:
            with sqlite3.connect(target) as dest:
                source.backup(dest)
