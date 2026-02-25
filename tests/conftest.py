"""Test configuration and fixtures."""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

from jose import jwt
import pytest
import pytest_asyncio
from faker import Faker
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
import os
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/test_rag_db"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENABLE_METRICS"] = "false"
os.environ["ENABLE_TRACING"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from app.core.config import Settings
from app.db.models import Base, ChatSession, Source, User
from app.db.sessions import get_db
from app.main import app
from app.utils.password import hash_password

# Initialize Faker
fake = Faker()

# Set pytest-asyncio mode
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Override settings for testing.
    
    Returns:
        Settings instance configured for testing with disabled Redis/metrics/tracing.
    """
    
    from app.core import config

    settings = Settings()
    # Ensure application code uses the test-specific settings instance
    config.settings = settings

    return settings


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_settings: Settings):
    """Create async SQLAlchemy engine for test database.
    
    Args:
        test_settings: Test configuration settings.
        
    Yields:
        SQLAlchemy async engine.
    """
    engine = create_async_engine(
        test_settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,  # Disable connection pooling for tests
    )
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def setup_test_db(test_engine):
    """Create all tables before tests, drop after.
    
    Args:
        test_engine: SQLAlchemy async engine.
    """
    from sqlalchemy import text
    
    async with test_engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def test_db_session(test_engine, setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Provide clean database session per test with automatic rollback.
    
    Args:
        test_engine: SQLAlchemy async engine.
        setup_test_db: Fixture ensuring tables exist.
        
    Yields:
        Clean AsyncSession that rolls back after test.
    """
    connection = await test_engine.connect()
    transaction = await connection.begin()
    
    async_session = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    session = async_session()
    
    yield session
    
    await session.close()
    await transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture
async def test_user(test_db_session: AsyncSession) -> User:
    """Create test user in database.
    
    Args:
        test_db_session: Clean database session.
        
    Returns:
        Test user instance.
    """
    user = User(
        email="test@example.com",
        username="testuser",
        password_hash=hash_password("testpassword123"),
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)
    return user


@pytest.fixture
def test_user_token(test_settings: Settings, test_user: User) -> str:
    """Generate valid JWT token for test user.
    
    Args:
        test_settings: Test configuration settings.
        test_user: Test user instance.
        
    Returns:
        JWT access token string.
    """
    payload = {
        "sub": str(test_user.id),
        "exp": datetime.utcnow() + timedelta(minutes=test_settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, test_settings.SECRET_KEY, algorithm="HS256")
    return token


@pytest.fixture
def auth_headers(test_user_token: str) -> dict[str, str]:
    """Return authorization headers with Bearer token.
    
    Args:
        test_user_token: JWT access token.
        
    Returns:
        Dictionary with Authorization header.
    """
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest_asyncio.fixture
async def client(test_db_session: AsyncSession, test_settings: Settings):
    """AsyncClient with dependency overrides.
    
    Args:
        test_db_session: Clean database session.
        test_settings: Test settings.
        
    Yields:
        AsyncClient instance with overridden dependencies.
    """
    async def override_get_db():
        yield test_db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, auth_headers: dict[str, str]) -> AsyncClient:
    """AsyncClient with auth headers pre-configured.
    
    Args:
        client: Base AsyncClient.
        auth_headers: Authorization headers.
        
    Returns:
        AsyncClient with default headers set.
    """
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def mock_embedder() -> Mock:
    """Mock HuggingFaceTEIEmbedder returning fake embeddings.
    
    Returns:
        Mock embedder with fake embed_query and embed_documents methods.
    """
    embedder = Mock()
    embedder.embed_query = AsyncMock(return_value=[0.1] * 768)
    embedder.embed_documents = AsyncMock(return_value=[[0.1] * 768])
    embedder.dimension = 768
    return embedder


@pytest.fixture
def mock_llm() -> Mock:
    """Mock ChatOllama returning fake responses.
    
    Returns:
        Mock LLM with fake ainvoke method.
    """
    llm = Mock()
    llm.ainvoke = AsyncMock(return_value="This is a fake LLM response.")
    return llm


@pytest.fixture
def mock_redis() -> Mock:
    """Mock Redis client.
    
    Returns:
        Mock Redis client with common methods.
    """
    redis = Mock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    return redis


@pytest.fixture
def mock_ingestion_service() -> Mock:
    """Mock ingestion application.
    
    Returns:
        Mock IngestionApplicationService with fake process_source method.
    """
    service = Mock()
    service.process_source = AsyncMock(
        return_value={
            "status": "completed",
            "chunks_created": 42,
            "processing_time_ms": 1500,
        }
    )
    return service


@pytest.fixture
def user_factory(test_db_session: AsyncSession):
    """Factory function to create test users.
    
    Args:
        test_db_session: Clean database session.
        
    Returns:
        Factory function that creates and returns User instances.
    """
    async def _create_user(
        email: str | None = None,
        username: str | None = None,
        password: str = "password123",
    ) -> User:
        user = User(
            email=email or fake.email(),
            username=username or fake.user_name(),
            password_hash=hash_password(password),
        )
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        return user
    
    return _create_user


@pytest.fixture
def source_factory(test_db_session: AsyncSession):
    """Factory function to create test sources.
    
    Args:
        test_db_session: Clean database session.
        
    Returns:
        Factory function that creates and returns Source instances.
    """
    from uuid import UUID
    
    async def _create_source(
        user_id: UUID,
        type: str = "pdf",
        title: str | None = None,
        status: str = "processing",
        source_uri: str | None = "default",
        collection_name: str | None = None,
    ) -> Source:
        # Use "default" sentinel to distinguish between None and not-provided
        if source_uri == "default":
            source_uri = f"file://test/{fake.file_name(extension='pdf')}"
        
        source = Source(
            user_id=user_id,
            type=type,
            title=title or fake.sentence(nb_words=4),
            status=status,
            source_uri=source_uri,
            collection_name=collection_name or f"test_collection_{fake.uuid4()}",
        )
        test_db_session.add(source)
        await test_db_session.commit()
        await test_db_session.refresh(source)
        return source
    
    return _create_source


@pytest.fixture
def chat_factory(test_db_session: AsyncSession):
    """Factory function to create test chats.
    
    Args:
        test_db_session: Clean database session.
        
    Returns:
        Factory function that creates and returns ChatSession instances.
    """
    from uuid import UUID
    
    async def _create_chat(
        user_id: UUID,
        title: str | None = None,
    ) -> ChatSession:
        chat = ChatSession(
            user_id=user_id,
            title=title or fake.sentence(nb_words=3),
        )
        test_db_session.add(chat)
        await test_db_session.commit()
        await test_db_session.refresh(chat)
        return chat
    
    return _create_chat
