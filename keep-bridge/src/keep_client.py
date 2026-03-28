from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import gkeepapi
from gkeepapi import node


@dataclass(frozen=True)
class KeepSnapshot:
    note_id: str
    title: str
    unchecked_items: list[str]
    checked_items: list[str]
    updated_at: str


class KeepClient(Protocol):
    def fetch_list(self, list_name: str) -> KeepSnapshot | None:
        ...

    def keepalive_sync(self) -> None:
        ...


class MockKeepClient:
    def __init__(self) -> None:
        self._counter = 0

    def fetch_list(self, list_name: str) -> KeepSnapshot | None:
        self._counter += 1
        normalized = list_name.strip().casefold()
        if normalized != "shopping list" and normalized != "shopping list mock":
            return None

        return KeepSnapshot(
            note_id="mock-note",
            title=list_name.strip() or "Shopping List",
            unchecked_items=["Milk", "Eggs", "Bread"],
            checked_items=["Apples"] if self._counter % 2 == 0 else [],
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    def keepalive_sync(self) -> None:
        return


class GoogleKeepClient:
    def __init__(self) -> None:
        self._email = require_env("KEEP_EMAIL")
        self._master_token = require_env("KEEP_MASTER_TOKEN")
        self._state_file = Path(os.getenv("KEEP_STATE_FILE", "keep_state.json"))

        self._keep = gkeepapi.Keep()
        state = self._load_state()
        try:
            # gkeepapi.authenticate returns None on success; failures raise exceptions.
            self._keep.authenticate(self._email, self._master_token, state=state)
        except Exception as error:  # noqa: BLE001
            raise RuntimeError(
                "Failed to authenticate with gkeepapi. Check KEEP_EMAIL and KEEP_MASTER_TOKEN."
            ) from error

    def keepalive_sync(self) -> None:
        self._sync_and_persist()

    def fetch_list(self, list_name: str) -> KeepSnapshot | None:
        lookup_name = list_name.strip()
        if not lookup_name:
            return None

        self._sync_and_persist()

        target_note = self._find_list_by_title(lookup_name)
        if target_note is None:
            return None

        unchecked_items = [item.text.strip() for item in target_note.unchecked if item.text and item.text.strip()]
        checked_items = [item.text.strip() for item in target_note.checked if item.text and item.text.strip()]

        updated_ts = target_note.timestamps.updated
        updated_at = updated_ts.isoformat() if updated_ts else datetime.now(tz=timezone.utc).isoformat()

        return KeepSnapshot(
            note_id=target_note.id,
            title=target_note.title.strip() if target_note.title else lookup_name,
            unchecked_items=unchecked_items,
            checked_items=checked_items,
            updated_at=updated_at,
        )

    def _sync_and_persist(self) -> None:
        self._keep.sync()
        self._save_state()

    def _find_list_by_title(self, title: str) -> node.List | None:
        title_folded = title.casefold()
        exact_matches: list[node.List] = []
        fuzzy_matches: list[node.List] = []

        for n in self._keep.all():
            if not isinstance(n, node.List):
                continue
            if n.trashed or n.deleted:
                continue

            note_title = (n.title or "").strip()
            note_title_folded = note_title.casefold()

            if note_title_folded == title_folded:
                exact_matches.append(n)
            elif title_folded in note_title_folded:
                fuzzy_matches.append(n)

        if exact_matches:
            return exact_matches[0]
        if fuzzy_matches:
            return fuzzy_matches[0]
        return None

    def _load_state(self) -> dict | None:
        if not self._state_file.exists():
            return None

        try:
            with self._state_file.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None

    def _save_state(self) -> None:
        state = self._keep.dump()
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        with self._state_file.open("w", encoding="utf-8") as fh:
            json.dump(state, fh)


def create_keep_client() -> KeepClient:
    use_mock = os.getenv("KEEP_USE_MOCK", "false").lower() == "true"
    if use_mock:
        return MockKeepClient()
    return GoogleKeepClient()


def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value
