from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jester.domain import Session


class StateStoreError(RuntimeError):
    """Raised when persistent state cannot be loaded or saved safely."""


class SessionConflictError(StateStoreError):
    """Raised when a session write loses a revision race."""


class SessionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    tenant_id: str = Field(default='default', min_length=1)
    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    payload_sha256: str = Field(min_length=1)
    session: Session

    @field_validator('tenant_id', 'session_id', 'campaign_id', 'payload_sha256', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Session record fields must not be blank.')
        return text


class StateStore(Protocol):
    def load_session(self, session_id: str) -> Session:
        ...

    def save_session(self, session: Session) -> None:
        ...


class SessionRepository(Protocol):
    def create_session(self, session: Session, *, tenant_id: str = 'default') -> SessionRecord:
        ...

    def load_session_record(self, session_id: str, *, tenant_id: str = 'default') -> SessionRecord:
        ...

    def save_session_record(
        self,
        record: SessionRecord,
        *,
        expected_revision: int | None = None,
    ) -> SessionRecord:
        ...

    def list_session_records(
        self,
        *,
        tenant_id: str = 'default',
        campaign_id: str | None = None,
    ) -> list[SessionRecord]:
        ...

    def check_health(self) -> bool:
        ...


class SQLiteSessionRepository(SessionRepository):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path.expanduser().resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def create_session(self, session: Session, *, tenant_id: str = 'default') -> SessionRecord:
        with self._connect() as connection:
            existing = connection.execute(
                'SELECT 1 FROM sessions WHERE tenant_id = ? AND session_id = ?',
                (tenant_id, session.session_id),
            ).fetchone()
        if existing is not None:
            raise StateStoreError(
                f'Session {session.session_id!r} already exists for tenant {tenant_id!r}.'
            )
        created = SessionRecord(
            tenant_id=tenant_id,
            session_id=session.session_id,
            campaign_id=session.campaign_id,
            revision=1,
            payload_sha256=_payload_sha(self._serialize_session(session)),
            session=session,
        )
        return self.save_session_record(created, expected_revision=0)

    def load_session_record(self, session_id: str, *, tenant_id: str = 'default') -> SessionRecord:
        with self._connect() as connection:
            row = connection.execute(
                '''
                SELECT tenant_id, session_id, campaign_id, revision, payload, payload_sha256
                FROM sessions
                WHERE tenant_id = ? AND session_id = ?
                ''',
                (tenant_id, session_id),
            ).fetchone()

        if row is None:
            raise StateStoreError(
                f'Session {session_id!r} was not found for tenant {tenant_id!r}.'
            )
        return self._row_to_record(row)

    def save_session_record(
        self,
        record: SessionRecord,
        *,
        expected_revision: int | None = None,
    ) -> SessionRecord:
        _validate_record(record)
        payload = self._serialize_session(record.session)
        payload_sha = _payload_sha(payload)

        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = connection.execute(
                    '''
                    SELECT revision
                    FROM sessions
                    WHERE tenant_id = ? AND session_id = ?
                    ''',
                    (record.tenant_id, record.session_id),
                ).fetchone()

                if row is None:
                    if expected_revision not in (None, 0):
                        raise SessionConflictError(
                            f'Expected revision {expected_revision} for missing session '
                            f'{record.session_id!r}.'
                        )
                    next_revision = 1
                    connection.execute(
                        '''
                        INSERT INTO sessions (
                            tenant_id,
                            session_id,
                            campaign_id,
                            revision,
                            payload,
                            payload_sha256,
                            created_at,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ''',
                        (
                            record.tenant_id,
                            record.session_id,
                            record.campaign_id,
                            next_revision,
                            payload,
                            payload_sha,
                        ),
                    )
                else:
                    current_revision = int(row['revision'])
                    if expected_revision is not None and current_revision != expected_revision:
                        raise SessionConflictError(
                            f'Session {record.session_id!r} revision conflict: '
                            f'expected {expected_revision}, current {current_revision}.'
                        )
                    next_revision = current_revision + 1
                    updated = connection.execute(
                        '''
                        UPDATE sessions
                        SET campaign_id = ?,
                            revision = ?,
                            payload = ?,
                            payload_sha256 = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tenant_id = ? AND session_id = ? AND revision = ?
                        ''',
                        (
                            record.campaign_id,
                            next_revision,
                            payload,
                            payload_sha,
                            record.tenant_id,
                            record.session_id,
                            current_revision,
                        ),
                    )
                    if updated.rowcount != 1:
                        raise SessionConflictError(
                            f'Session {record.session_id!r} could not be updated safely.'
                        )
            except sqlite3.DatabaseError as exc:
                connection.rollback()
                raise StateStoreError(
                    f'Failed to save session {record.session_id!r}: {exc}'
                ) from exc
            except SessionConflictError:
                connection.rollback()
                raise
            connection.commit()

        return SessionRecord(
            tenant_id=record.tenant_id,
            session_id=record.session_id,
            campaign_id=record.campaign_id,
            revision=next_revision,
            payload_sha256=payload_sha,
            session=record.session,
        )

    def list_session_records(
        self,
        *,
        tenant_id: str = 'default',
        campaign_id: str | None = None,
    ) -> list[SessionRecord]:
        sql = '''
            SELECT tenant_id, session_id, campaign_id, revision, payload, payload_sha256
            FROM sessions
            WHERE tenant_id = ?
        '''
        params: list[object] = [tenant_id]
        if campaign_id is not None:
            sql += ' AND campaign_id = ?'
            params.append(campaign_id)
        sql += ' ORDER BY campaign_id, session_id'

        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def check_health(self) -> bool:
        try:
            with self._connect() as connection:
                value = connection.execute('SELECT 1').fetchone()
        except sqlite3.DatabaseError:
            return False
        return value is not None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('PRAGMA journal_mode = WAL')
        connection.execute('PRAGMA synchronous = NORMAL')
        connection.execute('PRAGMA busy_timeout = 5000')
        return connection

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS sessions (
                    tenant_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, session_id)
                )
                '''
            )
            connection.execute(
                'CREATE INDEX IF NOT EXISTS idx_sessions_campaign_id ON sessions (tenant_id, campaign_id)'
            )
            connection.commit()

    def _row_to_record(self, row: sqlite3.Row) -> SessionRecord:
        payload = str(row['payload'])
        payload_sha = str(row['payload_sha256'])
        current_sha = _payload_sha(payload)
        if current_sha != payload_sha:
            raise StateStoreError(
                f"Stored payload checksum mismatch for session {row['session_id']!r}."
            )

        try:
            session = Session.model_validate_json(payload)
        except ValueError as exc:
            raise StateStoreError(
                f"Stored payload is invalid for session {row['session_id']!r}: {exc}"
            ) from exc

        return SessionRecord(
            tenant_id=str(row['tenant_id']),
            session_id=str(row['session_id']),
            campaign_id=str(row['campaign_id']),
            revision=int(row['revision']),
            payload_sha256=payload_sha,
            session=session,
        )

    @staticmethod
    def _serialize_session(session: Session) -> str:
        payload = session.model_dump(mode='json')
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class SQLiteStateStore(StateStore):
    def __init__(self, db_path: Path, *, tenant_id: str = 'default') -> None:
        self._tenant_id = tenant_id.strip() or 'default'
        self._repository = SQLiteSessionRepository(db_path)

    def load_session(self, session_id: str) -> Session:
        return self._repository.load_session_record(session_id, tenant_id=self._tenant_id).session

    def save_session(self, session: Session) -> None:
        record = SessionRecord(
            tenant_id=self._tenant_id,
            session_id=session.session_id,
            campaign_id=session.campaign_id,
            revision=1,
            payload_sha256=_payload_sha(SQLiteSessionRepository._serialize_session(session)),
            session=session,
        )
        self._repository.save_session_record(record)


def _validate_record(record: SessionRecord) -> None:
    if record.session.session_id != record.session_id:
        raise StateStoreError('Session record session_id must match embedded session.')
    if record.session.campaign_id != record.campaign_id:
        raise StateStoreError('Session record campaign_id must match embedded session.')


def _payload_sha(payload: str) -> str:
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
