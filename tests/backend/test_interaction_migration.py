"""Upgrade a populated v1 database, including outstanding work, without rewriting history."""

from alembic import command
from fastapi import FastAPI
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import migrations
from backend.domain.models import AgentRun, Feedback, Thread


async def test_populated_v1_migration_preserves_ids_history_and_legacy_policy(app: FastAPI) -> None:
    async with app.state.engine.connect() as connection:
        await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.execute(text("DROP DATABASE IF EXISTS interaction_migration"))
        await connection.execute(text("CREATE DATABASE interaction_migration"))
    engine = create_async_engine(app.state.engine.url.set(database="interaction_migration"))

    def seed(connection: Connection) -> None:
        connection.execute(text("CREATE SCHEMA app"))
        config = migrations.alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "0003")
        statements = [
            "INSERT INTO app.documents(id,document_type,title,current_version,created_by) VALUES ('d','brief','History',1,'fde')",
            "INSERT INTO app.threads(id,document_id,owner,title) VALUES ('t','d','fde','Conversation')",
            "INSERT INTO app.agent_runs(id,document_id,thread_id,run_kind,status,triggered_by,request_payload,response_payload,step_history,materialised_at) VALUES ('r','d','t','generate','succeeded','fde','{}','{\"output\":{\"history\":true}}','[]',now()), ('pending','d',NULL,'generate','accepted','fde','{}',NULL,'[]',NULL)",
            "INSERT INTO app.messages(id,thread_id,role,content,citations,agent_run_id) VALUES (7,'t','assistant','Historical answer','[]','r')",
            "INSERT INTO app.feedback(id,document_id,agent_run_id,kind,name,target,value,reasons,principal,revision,sync_status,sync_attempts) VALUES ('f','d','r','feedback','answer_rating','message:7','true','[]','fde',1,'synced',1)",
            "INSERT INTO app.document_versions(document_id,version,snapshot,agent_run_id,created_by) VALUES ('d',1,'{\"brief.summary\":\"Saved before migration\"}','r','fde')",
        ]
        for statement in statements:
            connection.exec_driver_sql(statement)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(seed)
        await migrations.upgrade(engine)
        async with async_sessionmaker(engine)() as db:
            run = await db.get(AgentRun, "r")
            pending = await db.get(AgentRun, "pending")
            thread = await db.get(Thread, "t")
            feedback = await db.get(Feedback, "f")
            assert run is not None
            assert pending is not None
            assert thread is not None
            assert feedback is not None
            assert (run.document_id, thread.document_id, feedback.document_id) == ("d", "d", "d")
            assert run.id == "r"
            assert run.response_payload == {"output": {"history": True}}
            assert pending.contract_version == "v1"
            assert pending.review_required is False
            assert run.review_required is False
            assert (
                await db.scalar(text("SELECT content FROM app.messages WHERE id=7"))
                == "Historical answer"
            )
            assert (
                await db.scalar(
                    text("SELECT snapshot->>'brief.summary' FROM app.document_versions")
                )
                == "Saved before migration"
            )
    finally:
        await engine.dispose()
