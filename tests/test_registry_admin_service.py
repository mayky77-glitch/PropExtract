from __future__ import annotations

from rns_import_server.registry_admin import RegistryAdminCode, RegistryAdminService
from rns_import_server.registry_storage import RegistryStorage


def service(tmp_path):
    storage = RegistryStorage.bootstrap(tmp_path)
    return storage, RegistryAdminService(storage)


def test_list_returns_generation_stable_binding_conflict_and_active_projection(tmp_path) -> None:
    storage, admin = service(tmp_path)
    try:
        listed = admin.list()
        assert listed.generation == storage.generation
        assert len(listed.constructions) == 4
        assert listed.routable_constructions == listed.constructions
        assert listed.bindings == () and listed.conflicts == ()
    finally:
        storage.close()


def test_provision_creates_draft_only_and_validates_duplicate_and_grammar(tmp_path) -> None:
    storage, admin = service(tmp_path)
    try:
        created = admin.create_provision_request(code_prefix="123-1234567", official_name="Новая", expected_generation=storage.generation)
        assert created.code is RegistryAdminCode.OK and created.construction is not None
        assert created.construction.status == "draft"
        assert created.construction not in admin.list().routable_constructions
        duplicate = admin.create_provision_request(code_prefix="123-1234567", official_name="Другая", expected_generation=storage.generation)
        invalid = admin.create_provision_request(code_prefix="١٢٣-١٢٣٤٥٦٧", official_name="Неверная", expected_generation=storage.generation)
        assert duplicate.code is RegistryAdminCode.DUPLICATE
        assert invalid.code is RegistryAdminCode.INVALID
    finally:
        storage.close()


def test_draft_correction_rejects_ordinary_activation_and_hard_delete_is_not_exposed(tmp_path) -> None:
    storage, admin = service(tmp_path)
    try:
        draft = admin.create_provision_request(code_prefix="123-1234567", official_name="Черновик", expected_generation=storage.generation).construction
        assert draft is not None
        corrected = admin.correct_draft(draft.id, code_prefix="123-1234568", official_name="Исправлен", expected_generation=storage.generation, expected_row_revision=draft.row_revision)
        assert corrected.code is RegistryAdminCode.OK and corrected.construction is not None
        assert corrected.construction.status == "draft"
        assert admin.change_status(draft.id, status="active", expected_generation=storage.generation).code is RegistryAdminCode.FORBIDDEN_STATUS_TRANSITION
        assert not hasattr(admin, "delete")
    finally:
        storage.close()


def test_bound_records_reject_name_code_change_but_allow_archive_and_revalidated_reactivation(tmp_path) -> None:
    storage, admin = service(tmp_path)
    try:
        active = storage.create_construction(code_prefix="123-1234567", official_name="Активная", status="active")
        storage.bind_construction(active.id, workbook_contract_id="contract", target_identity="target", sheet_identity="sheet", template_version="v1", verified_state="verified", expected_generation=storage.generation)
        assert admin.correct_draft(active.id, code_prefix="123-1234568", official_name="Новое", expected_generation=storage.generation, expected_row_revision=active.row_revision).code is RegistryAdminCode.BINDING_ALIGNMENT_REQUIRED
        archived = admin.change_status(active.id, status="archived", expected_generation=storage.generation)
        assert archived.code is RegistryAdminCode.OK and archived.construction is not None
        assert admin.change_status(active.id, status="active", expected_generation=storage.generation).code is RegistryAdminCode.BINDING_REVALIDATION_REQUIRED
        failed = admin.change_status(active.id, status="active", expected_generation=storage.generation, binding_revalidator=lambda binding: False)
        restored = admin.change_status(active.id, status="active", expected_generation=storage.generation, binding_revalidator=lambda binding: binding.verified_state == "verified")
        assert failed.code is RegistryAdminCode.BINDING_REVALIDATION_FAILED
        assert restored.code is RegistryAdminCode.OK and restored.construction is not None and restored.construction.status == "active"
    finally:
        storage.close()


def test_stale_generation_and_active_job_gate_are_typed_without_mutation(tmp_path) -> None:
    storage, admin = service(tmp_path)
    try:
        generation = storage.generation
        rejected = admin.create_provision_request(code_prefix="123-1234567", official_name="Занято", expected_generation=generation, active_job=True)
        waiting = admin.create_provision_request(code_prefix="123-1234567", official_name="Ожидание", expected_generation=generation, active_job=True, active_job_policy="wait")
        stale = admin.create_provision_request(code_prefix="123-1234567", official_name="Устарело", expected_generation=generation - 1)
        assert rejected.code is RegistryAdminCode.ACTIVE_JOB
        assert waiting.code is RegistryAdminCode.ACTIVE_JOB_WAIT_REQUIRED
        assert stale.code is RegistryAdminCode.STALE_GENERATION
        assert storage.get_construction("not-there") is None
    finally:
        storage.close()
