"""Tests for Alembic migrations — ensures upgrade/downgrade round-trip.

Uses pytest-alembic for migration testing in PostgreSQL test database.
Run: pytest tests/test_migrations.py -v
"""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import tempfile
import os


@pytest.fixture(scope="session")
def alembic_config():
    """Provide Alembic config for migrations."""
    config = Config("backend/alembic.ini")
    return config


@pytest.fixture(scope="session")
async def test_db_url():
    """Use test database for migration tests.
    
    Assumes: PostgreSQL running locally with superuser access
    or DATABASE_URL_TEST env var set to test DB connection string.
    """
    test_url = os.getenv(
        "DATABASE_URL_TEST",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/propops_test"
    )
    return test_url


@pytest.mark.asyncio
async def test_migration_001_upgrade(alembic_config, test_db_url):
    """Test migration 001 upgrade creates all Phase 1 tables with correct schema."""
    config = alembic_config
    config.set_main_option("sqlalchemy.url", test_db_url.replace("+asyncpg", ""))  # Alembic needs sync URL
    
    # Reset to initial state
    command.downgrade(config, "base")
    
    # Run upgrade
    command.upgrade(config, "001")
    
    # Connect and verify schema
    engine = create_async_engine(test_db_url, echo=False)
    async with engine.begin() as conn:
        # Verify tables exist
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        
        expected_tables = ["organizations", "properties", "units", "incidents"]
        for table in expected_tables:
            assert table in tables, f"Table {table} not created by migration 001"
        
        # Verify organizations columns
        org_columns = {col["name"] for col in inspector.get_columns("organizations")}
        assert "id" in org_columns
        assert "name" in org_columns
        assert "email_domain" in org_columns
        assert "plan" in org_columns
        assert "deleted_at" in org_columns
        
        # Verify incidents columns
        incident_columns = {col["name"] for col in inspector.get_columns("incidents")}
        assert "id" in incident_columns
        assert "org_id" in incident_columns
        assert "status" in incident_columns
        assert "category" in incident_columns
        assert "urgency" in incident_columns
        
        # Verify foreign keys exist
        fks = inspector.get_foreign_keys("properties")
        assert any(fk["constrained_columns"] == ["org_id"] for fk in fks), "properties.org_id FK missing"
        
        fks = inspector.get_foreign_keys("units")
        assert any(fk["constrained_columns"] == ["property_id"] for fk in fks), "units.property_id FK missing"
        
        fks = inspector.get_foreign_keys("incidents")
        assert any(fk["constrained_columns"] == ["org_id"] for fk in fks), "incidents.org_id FK missing"
        
        # Verify indexes exist
        org_indexes = {idx["name"] for idx in inspector.get_indexes("organizations")}
        assert "idx_organizations_deleted" in org_indexes
        assert "idx_organizations_email_domain" in org_indexes
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_001_downgrade(alembic_config, test_db_url):
    """Test migration 001 downgrade fully removes all Phase 1 tables."""
    config = alembic_config
    config.set_main_option("sqlalchemy.url", test_db_url.replace("+asyncpg", ""))
    
    # Run upgrade first
    command.upgrade(config, "001")
    
    # Then downgrade
    command.downgrade(config, "base")
    
    # Verify tables are gone
    engine = create_async_engine(test_db_url, echo=False)
    async with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        
        for table in ["organizations", "properties", "units", "incidents"]:
            assert table not in tables, f"Table {table} still exists after downgrade"
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_001_roundtrip(alembic_config, test_db_url):
    """Test full upgrade → downgrade → upgrade cycle (round-trip).
    
    Ensures downgrade() fully reverses upgrade() and re-running upgrade works.
    """
    config = alembic_config
    config.set_main_option("sqlalchemy.url", test_db_url.replace("+asyncpg", ""))
    
    # Cycle 1: upgrade
    command.upgrade(config, "001")
    
    # Cycle 2: downgrade
    command.downgrade(config, "base")
    
    # Cycle 3: upgrade again (should succeed with no errors)
    command.upgrade(config, "001")
    
    # Verify schema is consistent after round-trip
    engine = create_async_engine(test_db_url, echo=False)
    async with engine.begin() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        assert len(tables) == 4, "Expected 4 tables after round-trip"
        assert all(t in tables for t in ["organizations", "properties", "units", "incidents"])
    
    await engine.dispose()


def test_migration_001_downgrade_has_drop_statements():
    """Audit downgrade() to ensure it has drop_table calls for all tables."""
    from backend.alembic.versions import migration_001
    import inspect as insp
    
    # Get downgrade function source
    source = insp.getsource(migration_001.downgrade)
    
    # Verify