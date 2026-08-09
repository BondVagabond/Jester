from __future__ import annotations

from pathlib import Path

import pytest

from jester.state import SessionConflictError, SQLiteSessionRepository
from tests.runtime_factory import build_session


def test_session_repository_round_trip_and_revision_increment(tmp_path: Path) -> None:
    repository = SQLiteSessionRepository(tmp_path / 'state.sqlite3')
    session = build_session()

    created = repository.create_session(session, tenant_id='tenant-a')
    loaded = repository.load_session_record(session.session_id, tenant_id='tenant-a')
    loaded.session.name = 'Updated Session'

    saved = repository.save_session_record(loaded, expected_revision=loaded.revision)

    assert created.revision == 1
    assert saved.revision == 2
    reloaded = repository.load_session_record(session.session_id, tenant_id='tenant-a')
    assert reloaded.session.name == 'Updated Session'


def test_session_repository_rejects_stale_revision(tmp_path: Path) -> None:
    repository = SQLiteSessionRepository(tmp_path / 'state.sqlite3')
    session = build_session()
    repository.create_session(session, tenant_id='tenant-a')

    original = repository.load_session_record(session.session_id, tenant_id='tenant-a')
    stale = original.model_copy(deep=True)
    original.session.name = 'Fresh Update'
    repository.save_session_record(original, expected_revision=original.revision)

    stale.session.name = 'Stale Update'
    with pytest.raises(SessionConflictError):
        repository.save_session_record(stale, expected_revision=stale.revision)


def test_session_repository_isolates_by_tenant(tmp_path: Path) -> None:
    repository = SQLiteSessionRepository(tmp_path / 'state.sqlite3')
    first = build_session(session_id='session-shared')
    second = build_session(session_id='session-shared')
    second.name = 'Other Tenant Session'

    repository.create_session(first, tenant_id='tenant-a')
    repository.create_session(second, tenant_id='tenant-b')

    tenant_a = repository.load_session_record('session-shared', tenant_id='tenant-a')
    tenant_b = repository.load_session_record('session-shared', tenant_id='tenant-b')

    assert tenant_a.session.name == 'Copper Vault Session'
    assert tenant_b.session.name == 'Other Tenant Session'
