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
    cover_file      TEXT,            -- 本地封面文件（covers/ 下相对路径；空 = 未本地化）
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

CREATE TABLE IF NOT EXISTS tag_groups (
    group_name      TEXT PRIMARY KEY,
    tags            TEXT NOT NULL     -- 组内标签 JSON 数组
);

CREATE TABLE IF NOT EXISTS favorites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT,
    platform        TEXT,
    content_id      TEXT,
    fav_media_id    TEXT DEFAULT '',    -- 归属收藏夹（Bilibili media_id；抖音等无此概念为空串）
    fav_title       TEXT DEFAULT '',
    source          TEXT DEFAULT '',    -- 入库来源标记（空 = 收藏列表；如 喜欢列表 / 稍后再看列表）
    collected_at    TEXT,
    fetched_at      TEXT,
    UNIQUE(account_id, platform, content_id, fav_media_id, source)
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

CREATE TABLE IF NOT EXISTS downloads (
    download_id    TEXT PRIMARY KEY,
    platform       TEXT,
    content_id     TEXT,
    account_id     TEXT,                       -- 来源账号（下载时携带其 Cookies）
    title          TEXT,
    url            TEXT NOT NULL,
    downloader     TEXT DEFAULT 'yt-dlp',   -- yt-dlp / videodl
    status         TEXT DEFAULT 'pending',  -- pending / running / success / failed / canceled
    progress       TEXT,                    -- 下载器最近输出行（进度/阶段）
    output_path    TEXT,
    error_message  TEXT,
    created_at     TEXT,
    started_at     TEXT,
    finished_at    TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    type            TEXT DEFAULT 'info',   -- info / success / error
    title           TEXT NOT NULL,
    detail          TEXT,
    task_id         TEXT,
    read            INTEGER DEFAULT 0,
    created_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_favorites_account ON favorites(account_id, platform);
CREATE INDEX IF NOT EXISTS idx_tasks_started ON fetch_tasks(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_contents_platform ON contents(platform);
CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
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
                    source          TEXT DEFAULT '',
                    collected_at    TEXT,
                    fetched_at      TEXT,
                    UNIQUE(account_id, platform, content_id, fav_media_id, source)
                );
                INSERT INTO favorites_new (id, account_id, platform, content_id, fav_media_id,
                                           fav_title, source, collected_at, fetched_at)
                  SELECT id, account_id, platform, content_id, '', '', '', collected_at, fetched_at FROM favorites;
                DROP TABLE favorites;
                ALTER TABLE favorites_new RENAME TO favorites;
                CREATE INDEX IF NOT EXISTS idx_favorites_account ON favorites(account_id, platform);
                COMMIT;
            """)
        elif "source" not in fav_cols:
            # 加 source 来源标记并把唯一键扩为含 source：同一视频在收藏列表与
            # 喜欢/稍后再看列表各存一行；老数据 source='' 即收藏列表
            await self.conn.executescript("""
                BEGIN;
                CREATE TABLE favorites_new (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id      TEXT,
                    platform        TEXT,
                    content_id      TEXT,
                    fav_media_id    TEXT DEFAULT '',
                    fav_title       TEXT DEFAULT '',
                    source          TEXT DEFAULT '',
                    collected_at    TEXT,
                    fetched_at      TEXT,
                    UNIQUE(account_id, platform, content_id, fav_media_id, source)
                );
                INSERT INTO favorites_new (id, account_id, platform, content_id, fav_media_id,
                                           fav_title, source, collected_at, fetched_at)
                  SELECT id, account_id, platform, content_id, fav_media_id, fav_title, '',
                         collected_at, fetched_at FROM favorites;
                DROP TABLE favorites;
                ALTER TABLE favorites_new RENAME TO favorites;
                CREATE INDEX IF NOT EXISTS idx_favorites_account ON favorites(account_id, platform);
                COMMIT;
            """)

        async with self.conn.execute("PRAGMA table_info(contents)") as cur:
            content_cols = [row[1] for row in await cur.fetchall()]
        for col in ("tags", "tagged_at", "cover_file"):
            if col not in content_cols:
                await self.conn.execute(f"ALTER TABLE contents ADD COLUMN {col} TEXT")

        async with self.conn.execute("PRAGMA table_info(fetch_tasks)") as cur:
            task_cols = [row[1] for row in await cur.fetchall()]
        if "new_favorites" not in task_cols:
            await self.conn.execute("ALTER TABLE fetch_tasks ADD COLUMN new_favorites INTEGER")

        async with self.conn.execute("PRAGMA table_info(downloads)") as cur:
            dl_cols = [row[1] for row in await cur.fetchall()]
        if dl_cols and "account_id" not in dl_cols:
            await self.conn.execute("ALTER TABLE downloads ADD COLUMN account_id TEXT")
        if dl_cols and "quality" not in dl_cols:
            await self.conn.execute("ALTER TABLE downloads ADD COLUMN quality TEXT")

        # 标签分组：首次启动物化内置体系，此后编辑/新建分组均以库为准
        from app.taxonomy import BUILTIN_TAG_GROUPS

        row = await self.query_one("SELECT COUNT(*) AS n FROM tag_groups")
        if not row or row["n"] == 0:
            import json as _json

            for group, tags in BUILTIN_TAG_GROUPS:
                await self.conn.execute(
                    "INSERT OR IGNORE INTO tag_groups (group_name, tags) VALUES (?, ?)",
                    (group, _json.dumps(tags, ensure_ascii=False)),
                )

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

    async def executemany(self, sql: str, rows: list[tuple]) -> aiosqlite.Cursor:
        cur = await self.conn.executemany(sql, rows)
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
