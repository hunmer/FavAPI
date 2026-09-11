"""SQLite 数据层：共享连接管理 + PRD 表结构初始化。"""
import aiosqlite

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id      TEXT PRIMARY KEY,
    platform        TEXT NOT NULL,
    name            TEXT,
    status          TEXT DEFAULT 'active',
    profile_path    TEXT,
    last_login_at   TEXT,
    last_used_at    TEXT,
    created_at      TEXT,
    extra           TEXT
);

CREATE TABLE IF NOT EXISTS fetch_tasks (
    task_id         TEXT PRIMARY KEY,
    account_id      TEXT,
    platform        TEXT,
    action          TEXT,
    request_params  TEXT,
    status          TEXT,
    result_count    INTEGER,
    new_favorites   INTEGER,
    error_message   TEXT,
    started_at      TEXT,
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS contents (
    content_id      TEXT PRIMARY KEY,
    platform        TEXT NOT NULL,
    account_id      TEXT,
    title           TEXT,
    description     TEXT,
    author_id       TEXT,
    author_name     TEXT,
    cover_url       TEXT,
    duration        INTEGER,
    statistics      TEXT,
    raw_data        TEXT,
    first_seen_at   TEXT,
    last_seen_at    TEXT,
    tags            TEXT,             -- AI 打标结果（JSON 数组字符串）
    tagged_at       TEXT,
    UNIQUE(platform, content_id)
);

CREATE TABLE IF NOT EXISTS ai_agents (
    agent_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    base_url        TEXT NOT NULL,    -- OpenAI 兼容服务地址，如 https://api.openai.com/v1
    api_key         TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS favorites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT,
    platform        TEXT,
    content_id      TEXT,
    fav_media_id    TEXT DEFAULT '',    -- 归属收藏夹（Bilibili media_id；抖音等无此概念为空串）
    fav_title       TEXT DEFAULT '',
    collected_at    TEXT,
    fetched_at      TEXT,
    UNIQUE(account_id, platform, content_id, fav_media_id)
);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id    TEXT PRIMARY KEY,
    title          TEXT,
    account_id     TEXT NOT NULL,
    platform       TEXT NOT NULL,
    action         TEXT DEFAULT 'list_favorites',
    params         TEXT,
    cron_expr      TEXT NOT NULL,
    status         TEXT DEFAULT 'active',   -- active / paused
    last_run_at    TEXT,
    next_run_at    TEXT,
    last_task_id   TEXT,
    created_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_favorites_account ON favorites(account_id, platform);
CREATE INDEX IF NOT EXISTS idx_tasks_started ON fetch_tasks(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_contents_platform ON contents(platform);
CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(status, next_run_at);
"""


class Database:
    """整个应用共享一个 aiosqlite 连接（本地单用户服务，aiosqlite 内部串行执行）。"""

    def __init__(self, path):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._conn.commit()

    async def _migrate(self):
        """老库迁移。"""
        async with self.conn.execute("PRAGMA table_info(favorites)") as cur:
            fav_cols = [row[1] for row in await cur.fetchall()]
        if "fav_media_id" not in fav_cols:
            await self.conn.executescript("""
                BEGIN;
                CREATE TABLE favorites_new (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id      TEXT,
                    platform        TEXT,
                    content_id      TEXT,
                    fav_media_id    TEXT DEFAULT '',
                    fav_title       TEXT DEFAULT '',
                    collected_at    TEXT,
                    fetched_at      TEXT,
                    UNIQUE(account_id, platform, content_id, fav_media_id)
                );
                INSERT INTO favorites_new (id, account_id, platform, content_id, fav_media_id,
                                           fav_title, collected_at, fetched_at)
                  SELECT id, account_id, platform, content_id, '', '', collected_at, fetched_at FROM favorites;
                DROP TABLE favorites;
                ALTER TABLE favorites_new RENAME TO favorites;
                CREATE INDEX IF NOT EXISTS idx_favorites_account ON favorites(account_id, platform);
                COMMIT;
            """)

        async with self.conn.execute("PRAGMA table_info(contents)") as cur:
            content_cols = [row[1] for row in await cur.fetchall()]
        for col in ("tags", "tagged_at"):
            if col not in content_cols:
                await self.conn.execute(f"ALTER TABLE contents ADD COLUMN {col} TEXT")

        async with self.conn.execute("PRAGMA table_info(fetch_tasks)") as cur:
            task_cols = [row[1] for row in await cur.fetchall()]
        if "new_favorites" not in task_cols:
            await self.conn.execute("ALTER TABLE fetch_tasks ADD COLUMN new_favorites INTEGER")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("数据库尚未初始化（应用 lifespan 未执行）")
        return self._conn

    async def close(self):
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params=()) -> aiosqlite.Cursor:
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur

    async def query_one(self, sql: str, params=()) -> dict | None:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def query_all(self, sql: str, params=()) -> list[dict]:
        async with self.conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


db = Database(config.DB_PATH)
