from __future__ import annotations

from rns_import_server.group_provisioning import (
    GroupProvisioningCode, GroupProvisioningProjection, GroupProvisioningRequest,
    GroupProvisioningService, ProvisioningRow, plan_first_free_pair,
)
from rns_import_server.registry_admin import RegistryAdminService
from rns_import_server.registry_storage import RegistryStorage


class Projection:
    def __init__(self, storage, fixed_generation=None):
        self.storage, self.fixed_generation, self.digest = storage, fixed_generation, "hash"
        self.rows = tuple(
            [ProvisioningRow(number, {1: "data"}, True, True) for number in range(1, 606)]
            + [ProvisioningRow(606, {}, False, True), ProvisioningRow(607, {}, False, True)]
            + [ProvisioningRow(number, {25: "=formula"}, False, True) for number in range(608, 1002)]
        )
    def read_projection(self):
        generation = self.fixed_generation if self.fixed_generation is not None else self.storage.generation
        return GroupProvisioningProjection("book", self.digest, generation, self.rows)


class Pending:
    def reserve_pending_to_planning(self, action_id, *, job_authorization): return True


def test_formulas_in_business_columns_are_occupied_and_block_a_validated_pair() -> None:
    for column in (1, 24, 27):  # A, X, AA
        projection = GroupProvisioningProjection("book", "hash", 1, (
            ProvisioningRow(1, {1: "data"}, True, True),
            ProvisioningRow(2, {column: "=formula"}, True, True),
            ProvisioningRow(3, {}, False, True),
        ))
        assert plan_first_free_pair(projection) is None


def test_draft_plan_uses_business_occupancy_not_formula_tail_and_stays_non_routable(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        service = GroupProvisioningService(registry_admin=RegistryAdminService(storage), projections=Projection(storage), pending=Pending())
        result = service.submit(GroupProvisioningRequest("a", "new-job", "123-1234567", "Новая", storage.generation))
        assert result.code is GroupProvisioningCode.PLANNED and result.plan is not None
        assert (result.plan.header_row, result.plan.bootstrap_row) == (606, 607)
        assert result.draft is not None and result.draft.construction not in service._registry_admin.list().routable_constructions
    finally:
        storage.close()


def test_stale_generation_creates_no_second_draft_and_restarted_pending_needs_new_authorization(tmp_path) -> None:
    storage = RegistryStorage.bootstrap(tmp_path)
    try:
        service = GroupProvisioningService(registry_admin=RegistryAdminService(storage), projections=Projection(storage, storage.generation + 1), pending=Pending())
        stale = service.submit(GroupProvisioningRequest("a", "new-job", "123-1234567", "Новая", storage.generation))
        blocked = service.submit(GroupProvisioningRequest("b", None, "123-1234567", "Новая", storage.generation))
        assert stale.code is GroupProvisioningCode.STALE_GENERATION
        assert blocked.code is GroupProvisioningCode.JOB_AUTHORIZATION_REQUIRED
        assert all(item.official_name != "Новая" for item in service._registry_admin.list().constructions)

        draft = storage.create_construction(code_prefix="123-1234567", official_name="Новая", status="draft")
        fresh = Projection(storage); fresh.digest = "fresh-hash"
        resumed = GroupProvisioningService(registry_admin=RegistryAdminService(storage), projections=fresh, pending=Pending())
        replanned = resumed.replan_draft(
            GroupProvisioningRequest("restart", "new-job", "123-1234567", "Новая", storage.generation), draft_id=draft.id,
        )
        assert replanned.code is GroupProvisioningCode.PLANNED and replanned.plan is not None
        assert replanned.plan.workbook_hash == "fresh-hash" and replanned.plan.registry_generation == storage.generation
    finally:
        storage.close()
