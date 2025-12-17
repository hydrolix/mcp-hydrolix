"""FastAPI entrypoint with AG-UI endpoint."""

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from hdx_agent.config import get_settings, Config
from hdx_agent.agent import HydrolixAgent
from hdx_agent.config.log import setup_logging
from hdx_agent.graphs.db import DatabaseManager
from hdx_agent.graphs.entry import build_entry_graph
from ag_ui_langgraph.endpoint import add_langgraph_fastapi_endpoint


def init_graph_checkpoint_db(config: Config) -> DatabaseManager:
    db_manager = DatabaseManager(config.graph.memory)
    if db_manager.is_postgresql():
        with db_manager.get_connection() as conn:
            orig = conn.autocommit
            conn.set_autocommit(True)
            PostgresSaver(conn).setup()
            conn.set_autocommit(orig)
    else:
        with db_manager.get_connection() as conn:
            conn.execute("PRAGMA auto_vacuum = FULL;")

    return db_manager


async def create_checkpointer(config) -> BaseCheckpointSaver:
    """Create appropriate checkpointer based on config."""
    from hdx_agent.graphs.db import DatabaseManager

    db_manager = DatabaseManager(config.graph.memory)

    if db_manager.is_postgresql():
        pool = db_manager.aget_pool()
        await pool.open(wait=True)
        return AsyncPostgresSaver(pool)

    if db_manager.is_sqlite():
        logging.warning("Using SQLite checkpoint database")
        conn = await db_manager.aget_connection()
        return AsyncSqliteSaver(conn)

    if db_manager.is_inmemory():
        return InMemorySaver()

    raise ValueError("No valid checkpoint database configured")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="ClickHouse SQL Agent",
        description="An AI-powered SQL assistant for ClickHouse databases",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    setup_logging(None, "debug", "default")
    # cnf = Config()
    # db_manager = init_graph_checkpoint_db(cnf)
    # checkpointer = await create_checkpointer(cnf)

    # loop = asyncio.get_event_loop()
    # future = asyncio.ensure_future(create_checkpointer(cnf))
    # checkpointer = loop.run_until_complete(future)
    # # loop.close()

    checkpointer = InMemorySaver()
    entry_graph = build_entry_graph()
    compiled_graph = entry_graph.compile(checkpointer=checkpointer)

    agent = HydrolixAgent(
        name="clickhouse_sql_agent",
        description="A SQL assistant for ClickHouse databases",
        graph=compiled_graph,
    )

    add_langgraph_fastapi_endpoint(app, agent, "/agent")

    return app


app = create_app()


def main():
    settings = get_settings()

    uvicorn.run(
        # "hdx_agent.main:app",
        app,
        host=settings.server_host,
        port=settings.server_port,
        env_file=".env",
        # reload=True,
        # workers=1
    )


if __name__ == "__main__":
    main()
