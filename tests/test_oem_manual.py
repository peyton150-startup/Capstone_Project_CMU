"""Offline authorized OEM PDF import and scoped manual search tests."""

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

pytest.importorskip("sqlalchemy")

from capstone.manual.oem import (
    OEMApproval,
    OEMKnowledgeRepository,
    PrivatePDFStorage,
    ScopedOEMManualSearch,
    read_pdf,
)

PDF = b"%PDF-1.4\nprivate approved test document\n%%EOF\n"


def approval(**changes):
    values = {
        "document_id": "plant1.machine1.si-840d-maintenance",
        "revision": "v2",
        "title": "Approved Siemens maintenance reference",
        "site_id": "plant1",
        "machine_id": "machine1",
        "controller_family": "840D sl",
        "controller_fingerprint": "ncu-verified-1337",
        "approved_by": "Plant Technician",
        "approval_reference": "SIGNED-CONTRACT-2026-002",
        "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
        "pdf_sha256": hashlib.sha256(PDF).hexdigest(),
        "cloud_storage_approved": True,
        "retrieval_approved": True,
        "sections": [
            {
                "section_id": "5.2",
                "title": "Read-only fault reference",
                "text": "Read the approved spindle status, inspect the alarm condition, and verify the reading.",
                "page_start": 12,
                "page_end": 13,
            }
        ],
    }
    values.update(changes)
    return OEMApproval.model_validate(values)


def test_document_requires_namespaced_id_and_actual_human_scope():
    with pytest.raises(ValueError, match="namespaced"):
        approval(document_id="siemens-manual")
    with pytest.raises(PermissionError):
        approval(cloud_storage_approved=False).assert_active()
    with pytest.raises(PermissionError):
        approval(retrieval_approved=False).assert_active()
    with pytest.raises(PermissionError):
        approval(expires_at=datetime(2020, 1, 1, tzinfo=UTC)).assert_active()


def test_pdf_hash_and_repo_isolation_before_any_cloud_io(tmp_path, monkeypatch):
    from capstone.manual import oem

    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(PDF)
    entry = approval()
    # The repository pytest temp directory is deliberately not an allowed
    # production upload location. Preserve that check, then isolate hash tests.
    with pytest.raises(ValueError, match="outside the public Git checkout"):
        read_pdf(pdf, entry)
    monkeypatch.setattr(oem, "refusal", lambda *_: None)
    assert read_pdf(pdf, entry) == PDF
    pdf.write_bytes(PDF + b"unexpected modification")
    with pytest.raises(ValueError, match="SHA-256"):
        read_pdf(pdf, entry)


def test_same_revision_section_hash_captures_reviewed_page_edits():
    entry = approval()
    text = entry.sections[0].text
    edited = approval(
        sections=[
            {
                "section_id": "5.2",
                "title": "Read-only fault reference",
                "text": text + " This changes the reviewed text.",
                "page_start": 12,
                "page_end": 13,
            }
        ]
    )
    assert edited.section_digest != entry.section_digest
    assert entry.object_key.endswith(entry.pdf_sha256 + ".pdf")


class FakeStorage(PrivatePDFStorage):
    def __init__(self):
        super().__init__(
            origin="https://testproject.supabase.co",
            bucket="private-oem-documents",
            token="x" * 48,
        )
        self.saved = None
        self.attempts = 0

    def _assert_private_bucket(self):
        pass  # Simulates a verified private bucket.

    def _request(self, key, payload, method):
        if method == "POST":
            self.attempts += 1
            if self.saved is not None:
                raise HTTPError(
                    "https://example.invalid", 409, "Already exists", {}, None
                )
            self.saved = payload
            return BytesIO(b'{"Key":"uploaded"}')
        if method == "GET":
            return BytesIO(self.saved)
        raise AssertionError(method)


def test_private_storage_is_immutable_and_retry_requires_exact_pdf():
    store = FakeStorage()
    entry = approval()
    assert store.publish(entry, PDF) == entry.object_key
    assert store.publish(entry, PDF) == entry.object_key
    assert store.attempts == 2
    store.saved = b"tampered"
    with pytest.raises(ValueError, match="conflicts"):
        store.publish(entry, PDF)


def test_storage_refuses_public_bucket_and_non_supabase_or_http():
    for changes in [
        dict(origin="http://testproject.supabase.co"),
        dict(origin="https://evil.example.org"),
        dict(bucket="public-documents"),
    ]:
        options = dict(
            origin="https://testproject.supabase.co",
            bucket="private-oem-documents",
            token="x" * 48,
        )
        options.update(changes)
        with pytest.raises(ValueError, match="Private Supabase"):
            PrivatePDFStorage(**options)


class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return [
            {
                "document_id": "plant1.machine1.si-840d-maintenance",
                "revision": "v2",
                "section_id": "5.2",
                "title": "Approved Siemens maintenance reference",
                "body": "A matching authorized procedure from a reviewed page.",
            }
        ]


class FakeEngine:
    def __init__(self):
        self.calls = []

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, parameters):
        self.calls.append((str(sql), parameters))
        return FakeResult()


def test_oem_search_uses_exact_machine_and_controller_and_no_simulator():
    engine = FakeEngine()
    search = ScopedOEMManualSearch(
        engine,
        site_id="plant1",
        machine_id="machine1",
        controller_family="840D sl",
        controller_fingerprint="ncu-verified-1337",
    )
    found = search.search("spindle alarm", limit=3)
    assert found[0].document_id.startswith("plant1.machine1.")
    statement, params = engine.calls[0]
    for term in (
        "d.source_scope='pilot'",
        "d.is_published=TRUE",
        "a.expires_at > now()",
        "a.controller_fingerprint=:fingerprint",
        "a.site_id=:site",
        "a.machine_id=:machine",
    ):
        assert term in statement
    assert params["fingerprint"] == "ncu-verified-1337"
    assert params["query"] == "spindle alarm"
    with pytest.raises(ValueError):
        search.search("x", limit=99)


def test_oem_publication_requires_exact_private_object_and_unexpired_approval():
    store = OEMKnowledgeRepository(FakeEngine())
    with pytest.raises(ValueError, match="key differs"):
        store.publish(approval(), "unapproved/public.pdf")
    with pytest.raises(PermissionError):
        store.publish(approval(expires_at=datetime(2020, 1, 1, tzinfo=UTC)), "bad")


def test_oem_sql_migration_preserves_private_scope_and_lineage():
    source = (
        Path(__file__).resolve().parents[1] / "migrations/neon/0002_oem_approvals.sql"
    ).read_text()
    for fragment in (
        "manual_approvals",
        "controller_fingerprint",
        "approval_reference",
        "pdf_sha256",
        "section_sha256",
        "page_start",
        "page_end",
        "ENABLE ROW LEVEL SECURITY",
        "REVOKE ALL",
    ):
        assert fragment in source


def test_oem_private_conflict_recheck_uses_authenticated_storage_route(monkeypatch):
    """Private-object GET differs from the upload endpoint per Supabase API."""
    from capstone.manual import oem

    calls = []

    class LocalOpener:
        def open(self, request, timeout):
            calls.append((request.get_method(), request.full_url))
            return BytesIO(PDF)

    monkeypatch.setattr(oem, "build_opener", lambda *_: LocalOpener())
    storage = PrivatePDFStorage(
        origin="https://testproject.supabase.co",
        bucket="private-oem-documents",
        token="x" * 48,
    )
    key = approval().object_key
    with storage._request(key, PDF, "POST") as response:
        assert response.read() == PDF
    with storage._request(key, None, "GET") as response:
        assert response.read() == PDF
    assert calls == [
        (
            "POST",
            f"https://testproject.supabase.co/storage/v1/object/"
            f"private-oem-documents/{key}",
        ),
        (
            "GET",
            f"https://testproject.supabase.co/storage/v1/object/authenticated/"
            f"private-oem-documents/{key}",
        ),
    ]
