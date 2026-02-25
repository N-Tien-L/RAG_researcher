"""Utility script to set up test database."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base


async def create_test_database(database_url: str) -> None:
    """Create test database if it doesn't exist.
    
    Args:
        database_url: Database connection URL.
    """
    # Extract database name from URL
    db_name = database_url.split("/")[-1].split("?")[0]
    
    # Connect to postgres database to create test database
    postgres_url = database_url.replace(f"/{db_name}", "/postgres")
    
    engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    
    async with engine.connect() as conn:
        # Check if database exists
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": db_name},
        )
        exists = result.scalar() is not None
        
        if not exists:
            # Create database
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            print(f"Created test database: {db_name}")
        else:
            print(f"Test database already exists: {db_name}")
    
    await engine.dispose()


async def setup_test_database(database_url: str) -> None:
    """Set up test database with all tables.
    
    Args:
        database_url: Database connection URL.
    """
    # Create database if not exists
    await create_test_database(database_url)
    
    # Create tables
    engine = create_async_engine(database_url)
    
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("Created all tables in test database")
    
    await engine.dispose()


async def drop_test_database(database_url: str) -> None:
    """Drop test database.
    
    Args:
        database_url: Database connection URL.
    """
    # Extract database name from URL
    db_name = database_url.split("/")[-1].split("?")[0]
    
    # Connect to postgres database to drop test database
    postgres_url = database_url.replace(f"/{db_name}", "/postgres")
    
    engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    
    async with engine.connect() as conn:
        # Terminate existing connections
        await conn.execute(
            text(
                """
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = :dbname
                  AND pid <> pg_backend_pid()
                """
            ),
            {"dbname": db_name},
        )
        
        # Drop database
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        print(f"Dropped test database: {db_name}")
    
    await engine.dispose()


async def cleanup_test_database(database_url: str) -> None:
    """Drop all tables from test database.
    
    Args:
        database_url: Database connection URL.
    """
    engine = create_async_engine(database_url)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        print("Dropped all tables from test database")
    
    await engine.dispose()


async def main() -> None:
    """Main entry point for script."""
    import sys
    
    # Default test database URL
    test_db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/test_rag_db"
    
    if len(sys.argv) < 2:
        print("Usage: python setup_test_db.py [setup|drop|cleanup]")
        print(f"Using default database URL: {test_db_url}")
        action = "setup"
    else:
        action = sys.argv[1]
    
    if action == "setup":
        await setup_test_database(test_db_url)
    elif action == "drop":
        await drop_test_database(test_db_url)
    elif action == "cleanup":
        await cleanup_test_database(test_db_url)
    else:
        print(f"Unknown action: {action}")
        print("Valid actions: setup, drop, cleanup")


if __name__ == "__main__":
    asyncio.run(main())
