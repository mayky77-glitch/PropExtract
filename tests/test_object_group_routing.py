from __future__ import annotations

from rns_import_server.construction_registry import Construction
from rns_import_server.object_routing import (
    ConstructionRegistrySnapshot,
    ObjectRouteCode,
    route_object,
)
from rns_import_server.normalization import normalize_text


def construction(identifier: str, name: str, *, status: str = "active", code: str = "123-1234567") -> Construction:
    return Construction(
        id=identifier, seed_entry_id=None, origin="test", code_prefix=code,
        official_name=name, normalized_name=normalize_text(name), status=status,
        row_revision=1, created_at="2026-08-18T00:00:00Z", updated_at="2026-08-18T00:00:00Z",
    )


def snapshot(*constructions: Construction, generation: int = 7) -> ConstructionRegistrySnapshot:
    return ConstructionRegistrySnapshot.from_constructions(generation, constructions)


def test_exact_unicode_boundary_and_longest_prefix_preserve_raw_tail() -> None:
    parent = construction("parent", "Тестовая стройка", code="123-1234567")
    child = construction("child", "Тестовая стройка Этап 1", code="123-1234568")
    route = route_object("Тестовая\u00a0стройка Этап 1: Объект Ёлка", snapshot(parent, child))
    assert route.code is ObjectRouteCode.ROUTED
    assert route.construction_id == child.id
    assert route.code_prefix == child.code_prefix
    assert route.registry_generation == 7
    assert route.raw_object == "Тестовая\u00a0стройка Этап 1: Объект Ёлка"
    assert route.object_tail == "Объект Ёлка"
    assert route.can_create_new_row is True


def test_prefix_like_text_is_not_a_match_and_empty_tail_fails_closed() -> None:
    item = construction("one", "Стройка")
    assert route_object("СтройкаЭтап 1", snapshot(item)).code is ObjectRouteCode.UNKNOWN_CONSTRUCTION
    empty = route_object("Стройка — ", snapshot(item))
    assert empty.code is ObjectRouteCode.EMPTY_OBJECT_TAIL
    assert empty.construction_id == item.id
    assert empty.can_create_new_row is False


def test_unknown_conflicting_and_stale_snapshots_fail_closed() -> None:
    item = construction("one", "Стройка")
    assert route_object("Другая: объект", snapshot(item)).code is ObjectRouteCode.UNKNOWN_CONSTRUCTION
    duplicate = construction("two", "Стройка", code="123-1234568")
    assert route_object("Стройка: объект", snapshot(item, duplicate)).code is ObjectRouteCode.CONFLICTING_SNAPSHOT
    assert route_object("Стройка: объект", snapshot(item), expected_generation=6).code is ObjectRouteCode.STALE_REGISTRY


def test_draft_is_never_routable_and_archived_is_existing_only() -> None:
    draft = construction("draft", "Черновик", status="draft")
    archived = construction("archived", "Архив", status="archived", code="123-1234568")
    draft_route = route_object("Черновик: объект", snapshot(draft))
    assert draft_route.code is ObjectRouteCode.DRAFT_NOT_ROUTABLE
    assert draft_route.object_tail == "объект"
    new_archived = route_object("Архив: объект", snapshot(archived))
    assert new_archived.code is ObjectRouteCode.ARCHIVED_FOR_NEW_ROW
    existing_archived = route_object("Архив: объект", snapshot(archived), existing_construction_id="archived")
    assert existing_archived.code is ObjectRouteCode.ARCHIVED_EXISTING_ONLY
    assert existing_archived.can_create_new_row is False


def test_outcome_is_deterministic_and_tail_removes_only_matched_boundary() -> None:
    item = construction("one", "Стройка")
    source = "Стройка,  Объект — сохраняет Регистр"
    first = route_object(source, snapshot(item, generation=11))
    second = route_object(source, snapshot(item, generation=11))
    assert first == second
    assert first.object_tail == "Объект — сохраняет Регистр"
    assert first.raw_object == source
