import logging
import sqlite3
import tempfile
from contextlib import asynccontextmanager, contextmanager
from enum import Enum

import aiosqlite
from psycopg_pool import AsyncConnectionPool, ConnectionPool


class DatabaseType(Enum):
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class DatabaseManager:
    """
    Hybrid database abstraction layer providing both synchronous and asynchronous methods.
    Supports PostgreSQL and SQLite databases with connection pooling.
    """

    def __init__(self, config: dict) -> None:
        """
        Initialize DatabaseManager with configuration.

        Args:
            config: Dict containing database configuration
                Example:
                {
                    'postgresql': {
                        'username': 'user',
                        'password': 'pass',
                        'host': 'localhost',
                        'port': 5432,
                        'database': 'mydb',
                        'pool': {'min_size': 2, 'max_size': 10}
                    }
                }
                or
                {
                    'sqlite': {
                        'path': '/path/to/db.sqlite'
                    }
                }
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Connection pools and connections
        self._pg_async_pool_opened = False
        self._pg_sync_pool_opened = False
        self._pg_async_pool: AsyncConnectionPool | None = None
        self._pg_sync_pool: ConnectionPool | None = None
        self._sqlite_path: str | None = None
        self._current_db_type: DatabaseType | None = None

        self.initialize()

    def initialize(self) -> None:
        """Initialize connection pools for the specified database type."""
        if "postgresql" in self.config:
            self._initialize_postgresql()
            self._current_db_type = DatabaseType.POSTGRESQL
        elif "sqlite" in self.config:
            self._initialize_sqlite()
            self._current_db_type = DatabaseType.SQLITE
        else:
            raise ValueError("No database configured. Provide 'postgresql' or 'sqlite' config.")

    def _initialize_postgresql(self) -> None:
        """Initialize PostgreSQL connection pools (both sync and async)."""
        pgc = self.config.get("postgresql", {})
        pool_config = pgc.get("pool", {})

        conninfo = f"postgresql://{pgc.username}:{pgc.password}@{pgc.host}:{pgc.port}/{pgc.database}"

        # Async pool
        self._pg_async_pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=pool_config.get("min_size", 2),
            max_size=pool_config.get("max_size", 10),
            kwargs={"prepare_threshold": None},
            open=False,
        )

        # Sync pool
        self._pg_sync_pool = ConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=1,
            open=False,
        )

        log_config = pgc.copy()
        log_config["username"] = log_config["username"][:4] + "******"
        log_config["password"] = "******"  # noqa: S105
        self.logger.info(f"PostgreSQL pools initialized (async={log_config})")

    def _initialize_sqlite(self) -> None:
        """Initialize SQLite configuration."""
        sqlite_config = self.config.get("sqlite", {})
        self._sqlite_path = sqlite_config.get(
            "path", tempfile.mkstemp(suffix=".sqlite", prefix="db-manager-", text=False)[1]
        )
        self.logger.info(f"SQLite configuration loaded (path={self._sqlite_path})")

    # ==================== SYNCHRONOUS METHODS ====================

    @contextmanager
    def get_connection(self):  # noqa: ANN201
        """
        Synchronous context manager to get a database connection.

        Yields:
            Database connection object

        Example:
            with db_manager.get_connection_sync() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
        """
        if self._current_db_type == DatabaseType.POSTGRESQL:
            if not self._pg_sync_pool_opened:
                self._pg_sync_pool.open()
                self._pg_sync_pool_opened = True

            conn = self._pg_sync_pool.getconn()
            try:
                yield conn
            finally:
                self._pg_sync_pool.putconn(conn)

        elif self._current_db_type == DatabaseType.SQLITE:
            conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
            try:
                yield conn
            finally:
                conn.close()
        else:
            raise RuntimeError("Database not initialized. Call initialize() first.")

    @contextmanager
    def get_cursor(self, commit: bool = False):  # noqa: ANN201
        """
        Synchronous context manager to get a database cursor.

        Args:
            commit: Whether to commit the transaction after cursor operations

        Yields:
            Database cursor object

        Example:
            with db_manager.get_cursor_sync(commit=True) as cursor:
                cursor.execute("INSERT INTO users (name) VALUES (?)", ("John",))
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                if commit:
                    conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    def close(self) -> None:
        """Close synchronous database connections and cleanup resources."""
        if self._pg_sync_pool:
            self._pg_sync_pool.close()
            self.logger.info("PostgreSQL sync connection pool closed")

    # ==================== ASYNCHRONOUS METHODS ====================

    @asynccontextmanager
    async def aget_connection(self):  # noqa: ANN201
        """
        Asynchronous context manager to get a database connection.

        Yields:
            Database connection object

        Example:
            async with db_manager.get_connection() as conn:
                cursor = await conn.cursor()
                await cursor.execute("SELECT * FROM users")
        """
        if self._current_db_type == DatabaseType.POSTGRESQL:
            if not self._pg_async_pool_opened:
                await self._pg_async_pool.open()
                self._pg_async_pool_opened = True

            conn = await self._pg_async_pool.getconn()
            try:
                yield conn
            finally:
                await self._pg_async_pool.putconn(conn)

        elif self._current_db_type == DatabaseType.SQLITE:
            conn = await aiosqlite.connect(self._sqlite_path, check_same_thread=False)
            try:
                yield conn
            finally:
                await conn.close()
        else:
            raise RuntimeError("Database not initialized. Call initialize() first.")

    @asynccontextmanager
    async def aget_cursor(self, commit: bool = False):  # noqa: ANN201
        """
        Asynchronous context manager to get a database cursor.

        Args:
            commit: Whether to commit the transaction after cursor operations

        Yields:
            Database cursor object

        Example:
            async with db_manager.get_cursor(commit=True) as cursor:
                await cursor.execute("INSERT INTO users (name) VALUES (?)", ("John",))
        """
        async with self.aget_connection() as conn:
            cursor = await conn.cursor()
            try:
                yield cursor
                if commit:
                    await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise e
            finally:
                await cursor.close()

    async def aclose(self) -> None:
        """Close asynchronous database connections and cleanup resources."""
        if self._pg_async_pool:
            await self._pg_async_pool.close()
            self.logger.info("PostgreSQL async connection pool closed")

    # ==================== CONTEXT MANAGER SUPPORT ====================

    def __enter__(self):  # noqa: ANN204
        """Support using DatabaseManager as a synchronous context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # noqa: ANN001, ANN204
        """Cleanup when exiting synchronous context manager."""
        self.close()

    async def __aenter__(self):  # noqa: ANN204
        """Support using DatabaseManager as an asynchronous context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):  # noqa: ANN001, ANN204
        """Cleanup when exiting asynchronous context manager."""
        await self.aclose()

    # ==================== UTILITY METHODS ====================

    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL."""
        return self._current_db_type == DatabaseType.POSTGRESQL

    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self._current_db_type == DatabaseType.SQLITE

    def is_inmemory(self) -> bool:
        """For tests only."""
        return False

    def get_db_type(self) -> DatabaseType | None:
        """Get current database type."""
        return self._current_db_type

    def aget_pool(self) -> AsyncConnectionPool | None:
        """Get async connection pool (PostgreSQL only)."""
        return self._pg_async_pool

    def get_pool(self) -> ConnectionPool | None:
        """Get sync connection pool (PostgreSQL only)."""
        return self._pg_sync_pool
