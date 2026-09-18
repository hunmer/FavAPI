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
    progress        TEXT,                -- 运行中进度摘要（第 N 批 · 累计 X 条；终态清空）
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
    cover_file      INTEGER DEFAULT 0,   -- 封面是否已本地化（1 = data/covers 已落盘）
    duration        INTEGER,
    statistics      TEXT,
    published_at    TEXT,                -- 发布日期 YYYY-MM-DD（本地时区；缺失为 NULL）
    tags            TEXT,                -- AI 打标结果（JSON 数组字符串）
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

CREATE TABLE IF NOT EXISTS follow_authors (
    sec_uid        TEXT PRIMARY KEY,      -- 博主 sec_user_id（添加即特别关注）
    platform       TEXT NOT NULL DEFAULT 'douyin',
    account_id     TEXT,                  -- 添加时所用账号（后续同步/浏览用其登录态）
    uid            TEXT DEFAULT '',       -- 博主 uid（与作品 author_id 匹配未读数用）
    nickname       TEXT,
    unique_id      TEXT,
    avatar_url     TEXT,
    signature      TEXT,
    follower_count INTEGER,
    group_name     TEXT DEFAULT '',       -- 分组名（空 = 未分组）
    created_at     TEXT,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS follow_reads (
    content_id     TEXT PRIMARY KEY,      -- 已读的作品（特别关注场景）
    read_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_favorites_account ON favorites(account_id, platform);
CREATE INDEX IF NOT EXISTS idx_tasks_started ON fetch_tasks(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_contents_platform ON contents(platform);
CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_follow_authors_account ON follow_authors(account_id);
CREATE INDEX IF NOT EXISTS idx_follow_reads_read ON follow_reads(read_at DESC);
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

        if "raw_data" in content_cols:
            await self._migrate_contents_v2()
        elif "published_at" not in content_cols:
            await self.conn.execute("ALTER TABLE contents ADD COLUMN published_at TEXT")

        async with self.conn.execute("PRAGMA table_info(fetch_tasks)") as cur:
            task_cols = [row[1] for row in await cur.fetchall()]
        if "new_favorites" not in task_cols:
            await self.conn.execute("ALTER TABLE fetch_tasks ADD COLUMN new_favorites INTEGER")
        if "progress" not in task_cols:
            await self.conn.execute("ALTER TABLE fetch_tasks ADD COLUMN progress TEXT")

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

    async def _migrate_contents_v2(self):
        """contents v2：raw_data 外置为 data/raw_data/{platform}/{id}.json 文件；
        cover_file 由封面相对路径改为 0/1 标记；移除 first_seen_at / last_seen_at；
        新增 published_at（发布日期过滤原依赖库内 raw_data 计算）。
        先导出文件再重建表：中途失败旧表原样保留，重跑幂等。"""
        from app.services import raw_store

        rows = await self.query_all(
            "SELECT platform, content_id, raw_data FROM contents"
            " WHERE raw_data IS NOT NULL AND raw_data != ''"
        )
        for r in rows:
            raw_store.save(r["platform"], r["content_id"], r["raw_data"])
        await self.conn.executescript("""
            BEGIN;
            CREATE TABLE contents_new (
                content_id      TEXT PRIMARY KEY,
                platform        TEXT NOT NULL,
                account_id      TEXT,
                title           TEXT,
                description     TEXT,
                author_id       TEXT,
                author_name     TEXT,
                cover_url       TEXT,
                cover_file      INTEGER DEFAULT 0,
                duration        INTEGER,
                statistics      TEXT,
                published_at    TEXT,
                tags            TEXT,
                tagged_at       TEXT,
                UNIQUE(platform, content_id)
            );
            INSERT INTO contents_new (content_id, platform, account_id, title, description,
                author_id, author_name, cover_url, cover_file, duration, statistics,
                published_at, tags, tagged_at)
              SELECT content_id, platform, account_id, title,
                     CASE WHEN description IS NOT NULL AND description = title
                          THEN '' ELSE description END,
                     author_id, author_name, cover_url,
                     CASE WHEN cover_file IS NOT NULL AND cover_file != '' THEN 1 ELSE 0 END,
                     duration, statistics,
                     date(COALESCE(json_extract(raw_data, '$.create_time'),
                                   json_extract(raw_data, '$.ctime'),
                                   json_extract(raw_data, '$.createTime')),
                          'unixepoch', 'localtime'),
                     tags, tagged_at
                FROM contents;
            DROP TABLE contents;
            ALTER TABLE contents_new RENAME TO contents;
            CREATE INDEX IF NOT EXISTS idx_contents_platform ON contents(platform);
            COMMIT;
        """)
        await self.conn.executescript("VACUUM;")  # 回收 raw_data 移出后的空闲页

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
