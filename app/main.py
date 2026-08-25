from contextlib import asynccontextmanager
from pathlib import Path
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.registry import close_all
from app.api.routes import (
    accounts,
    channels,
    config,
    drill,
    job_rules,
    jobs,
    marks,
    resume_loop,
    resumes,
    save,
    sops,
    scraped,
    search,
    telegram_auth,
    telegram_ops,
    value_tags,
)
from app.core.config import settings
from app.core.telegram_client import close_all_clients


def _run_migrations():
    from app.db.connection import engine
    from app.db.schema import Base
    from sqlalchemy import text
    import logging

    _log = logging.getLogger(__name__)
    if not engine:
        return
    try:
        Base.metadata.create_all(engine, checkfirst=True)
    except Exception as e:
        _log.error("create_all failed: %s", e)
        return
    try:
        with engine.begin() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(text(
                    "ALTER TABLE channel_sync_runs ADD COLUMN IF NOT EXISTS query TEXT DEFAULT ''"
                ))
                conn.execute(text(
                    "ALTER TABLE channel_sync_runs ADD COLUMN IF NOT EXISTS parsed_query JSON"
                ))
            else:
                sync_cols = {
                    row[1]
                    for row in conn.execute(text("PRAGMA table_info(channel_sync_runs)")).fetchall()
                }
                if "query" not in sync_cols:
                    conn.execute(text(
                        "ALTER TABLE channel_sync_runs ADD COLUMN query TEXT DEFAULT ''"
                    ))
                if "parsed_query" not in sync_cols:
                    conn.execute(text(
                        "ALTER TABLE channel_sync_runs ADD COLUMN parsed_query JSON"
                    ))
            conn.execute(text(
                "UPDATE channel_sync_runs "
                "SET status = 'failed', error = '服务重启，任务被中断', "
                "finished_at = CURRENT_TIMESTAMP "
                "WHERE status IN ('queued', 'running')"
            ))
    except Exception as e:
        _log.warning("Recover interrupted channel sync runs skipped: %s", e)
    try:
        with engine.begin() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(text(
                    "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS final_markdown TEXT DEFAULT ''"
                ))
            else:
                rows = conn.execute(text("PRAGMA table_info(resumes)")).fetchall()
                cols = {r[1] for r in rows}
                if rows and "final_markdown" not in cols:
                    conn.execute(text(
                        "ALTER TABLE resumes ADD COLUMN final_markdown TEXT DEFAULT ''"
                    ))
                sug = conn.execute(text("PRAGMA table_info(resume_suggestions)")).fetchall()
                sug_cols = {r[1] for r in sug}
                if sug and "kind" not in sug_cols:
                    conn.execute(text(
                        "ALTER TABLE resume_suggestions ADD COLUMN kind VARCHAR(16) DEFAULT 'optimize'"
                    ))
                sops = conn.execute(text("PRAGMA table_info(resume_sops)")).fetchall()
                sop_cols = {r[1] for r in sops}
                if sops and "description" not in sop_cols:
                    conn.execute(text(
                        "ALTER TABLE resume_sops ADD COLUMN description TEXT DEFAULT ''"
                    ))
                if sops and "brief" not in sop_cols:
                    conn.execute(text("ALTER TABLE resume_sops ADD COLUMN brief TEXT DEFAULT ''"))
                if sops and "models" not in sop_cols:
                    conn.execute(text("ALTER TABLE resume_sops ADD COLUMN models JSON"))
                if sops and "resume_id" not in sop_cols:
                    conn.execute(text("ALTER TABLE resume_sops ADD COLUMN resume_id INTEGER"))
                if sops and "status" not in sop_cols:
                    conn.execute(text(
                        "ALTER TABLE resume_sops ADD COLUMN status VARCHAR(16) DEFAULT 'draft'"
                    ))
                if sops and "purpose" not in sop_cols:
                    conn.execute(text(
                        "ALTER TABLE resume_sops ADD COLUMN purpose VARCHAR(16) DEFAULT 'analyze'"
                    ))
    except Exception as e:
        _log.warning("Migration resumes.final_markdown skipped: %s", e)
    try:
        with engine.begin() as conn:
            scraped_cols_sql = {
                "core_tags": "JSON",
                "regions": "JSON",
                "is_remote": "BOOLEAN DEFAULT 0",
                "interest_tags": "JSON",
                "preference_score": "INTEGER DEFAULT 0",
                "salary_min_usd": "INTEGER DEFAULT 0",
                "salary_max_usd": "INTEGER DEFAULT 0",
                "salary_bucket": "VARCHAR(32) DEFAULT ''",
                "data_quality_ok": "BOOLEAN DEFAULT 1",
                "value_score": "INTEGER DEFAULT 50",
                "value_tags": "JSON",
                "derived_at": "DATETIME",
                "salary_cny": "VARCHAR(64) DEFAULT ''",
                "filtered_out": "BOOLEAN DEFAULT 0",
                "ai_gate_score": "INTEGER DEFAULT -1",
                "ai_gate_reason": "VARCHAR(160) DEFAULT ''",
            }
            if engine.dialect.name == "postgresql":
                for col, decl in scraped_cols_sql.items():
                    conn.execute(text(f"ALTER TABLE scraped_jobs ADD COLUMN IF NOT EXISTS {col} {decl}"))
            else:
                sj = conn.execute(text("PRAGMA table_info(scraped_jobs)")).fetchall()
                sj_cols = {r[1] for r in sj}
                if sj:
                    for col, decl in scraped_cols_sql.items():
                        if col not in sj_cols:
                            conn.execute(text(f"ALTER TABLE scraped_jobs ADD COLUMN {col} {decl}"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scraped_jobs_channel ON scraped_jobs (channel)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scraped_jobs_match_score ON scraped_jobs (match_score)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scraped_jobs_posted_at ON scraped_jobs (posted_at)"))

            if engine.dialect.name == "postgresql":
                conn.execute(text(
                    "ALTER TABLE job_value_tags ADD COLUMN IF NOT EXISTS source VARCHAR(16) DEFAULT 'manual'"
                ))
            else:
                jvt = conn.execute(text("PRAGMA table_info(job_value_tags)")).fetchall()
                jvt_cols = {r[1] for r in jvt}
                if jvt and "source" not in jvt_cols:
                    conn.execute(text(
                        "ALTER TABLE job_value_tags ADD COLUMN source VARCHAR(16) DEFAULT 'manual'"
                    ))
    except Exception as e:
        _log.warning("Migration scraped_jobs derived columns skipped: %s", e)
    try:
        with engine.begin() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(text(
                    "ALTER TABLE resume_suggestions ADD COLUMN IF NOT EXISTS kind VARCHAR(16) DEFAULT 'optimize'"
                ))
                conn.execute(text(
                    "ALTER TABLE resume_sops ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''"
                ))
                conn.execute(text(
                    "ALTER TABLE resume_sops ADD COLUMN IF NOT EXISTS brief TEXT DEFAULT ''"
                ))
                conn.execute(text(
                    "ALTER TABLE resume_sops ADD COLUMN IF NOT EXISTS models JSON"
                ))
                conn.execute(text(
                    "ALTER TABLE resume_sops ADD COLUMN IF NOT EXISTS resume_id INTEGER"
                ))
                conn.execute(text(
                    "ALTER TABLE resume_sops ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'draft'"
                ))
                conn.execute(text(
                    "ALTER TABLE resume_sops ADD COLUMN IF NOT EXISTS purpose VARCHAR(16) DEFAULT 'analyze'"
                ))
    except Exception as e:
        _log.warning("Migration resume_suggestions.kind skipped: %s", e)
    # 这段补丁只适用于历史 PostgreSQL 库；Turso/SQLite 的新表由 create_all 建约束。
    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uq_tg_classify'
                    ) THEN
                        -- 先删重复行，保留 id 最小的
                        DELETE FROM tg_classify_cache a USING tg_classify_cache b
                        WHERE a.id > b.id
                          AND a.account_id = b.account_id
                          AND a.target = b.target
                          AND a.msg_id = b.msg_id;
                        ALTER TABLE tg_classify_cache
                        ADD CONSTRAINT uq_tg_classify UNIQUE (account_id, target, msg_id);
                    END IF;
                END $$;
            """)
            )
    except Exception as e:
        _log.warning("Migration uq_tg_classify skipped: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    try:
        from app.core.job_rules import seed_job_rules
        n = seed_job_rules()
        if n:
            import logging
            logging.getLogger(__name__).info("seeded job_rules: %s rows", n)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("seed job_rules skipped: %s", e)
    Thread(target=scraped.warm_scraped_catalog, daemon=True).start()
    yield
    await close_all()
    await close_all_clients()


app = FastAPI(
    title="Scraper",
    description="AI-native multi-channel data scraper",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(search.router)
app.include_router(channels.router)
app.include_router(save.router)
app.include_router(scraped.router)
app.include_router(marks.router)
app.include_router(jobs.router)
app.include_router(accounts.router)
app.include_router(config.router)
app.include_router(drill.router)
app.include_router(telegram_auth.router)
app.include_router(telegram_ops.router)
app.include_router(resumes.router)
app.include_router(resume_loop.router)
app.include_router(sops.router)
app.include_router(value_tags.router)
app.include_router(job_rules.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


STATIC_DIR = Path(__file__).parent / "static"

if (STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
if (STATIC_DIR / "icons").is_dir():
    app.mount("/icons", StaticFiles(directory=STATIC_DIR / "icons"), name="icons")


@app.get("/manifest.json")
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


# SPA fallback：必须最后注册，否则会抢在 /api/* 之前匹配掉请求
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "health", "assets/", "icons/")):
        raise HTTPException(status_code=404)
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store, max-age=0"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
