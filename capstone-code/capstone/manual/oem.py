"""Explicit, human-authorized OEM PDF import and machine-matched Neon retrieval.

PDF extraction and OCR are deliberately not delegated to an LLM. An operator
must review/approve the text and page numbers in the manifest before --apply.
No OEM document or source is placed into the public Git repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from capstone.ingestion.privacy import refusal
from capstone.manual.neon import open_neon_manual
from capstone.manual.sections import ManualSection

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_PDF_BYTES = 12 * 1024 * 1024


class ReviewedOEMSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    section_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=180)
    text: str = Field(min_length=20, max_length=8000)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def valid_pages(self):
        if self.page_end < self.page_start:
            raise ValueError("manual section page range is inverted")
        return self


class OEMApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    document_id: str
    revision: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    site_id: str
    machine_id: str
    controller_family: Literal["840D sl", "828D", "SINUMERIK ONE"]
    controller_fingerprint: str = Field(min_length=8, max_length=180)
    approved_by: str = Field(min_length=2, max_length=120)
    approval_reference: str = Field(min_length=8, max_length=180)
    expires_at: AwareDatetime
    pdf_sha256: str
    cloud_storage_approved: bool = False
    retrieval_approved: bool = False
    embedding_egress_approved: bool = False
    sections: tuple[ReviewedOEMSection, ...] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_scope(self):
        for ident in (self.site_id, self.machine_id):
            if not _ID.fullmatch(ident) or len(ident) > 64:
                raise ValueError("invalid site or machine ID")
        if not _ID.fullmatch(self.document_id) or not self.document_id.startswith(
            f"{self.site_id}.{self.machine_id}."
        ):
            raise ValueError("document ID must be site/machine namespaced")
        if not re.fullmatch(r"[a-f0-9]{64}", self.pdf_sha256):
            raise ValueError("invalid source PDF digest")
        ids = [s.section_id for s in self.sections]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate OEM manual section")
        return self

    def assert_active(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if (
            self.expires_at <= now
            or not self.cloud_storage_approved
            or not self.retrieval_approved
        ):
            raise PermissionError("OEM document approval expired or incomplete")

    @property
    def section_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                [s.model_dump() for s in self.sections],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @property
    def object_key(self) -> str:
        return (
            f"{self.site_id}/{self.machine_id}/{self.document_id}/"
            f"{self.revision}/{self.pdf_sha256}.pdf"
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class PrivatePDFStorage:
    """Private Supabase Storage REST upload. Never accepts a public bucket."""

    def __init__(self, *, origin: str, token: str, bucket: str):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith(".supabase.co")
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or not re.fullmatch(r"[a-z0-9-]{3,63}", bucket)
            or not bucket.startswith("private-")
            or len(token) < 32
        ):
            raise ValueError("Private Supabase Storage configuration invalid")
        self.origin = origin.rstrip("/")
        self.token = token
        self.bucket = bucket

    def _request(self, key: str, payload: bytes | None, method: str):
        # Supabase private downloads require the authenticated route; the
        # upload route is POST /object/<bucket>/<key> and must not be reused
        # for checking a 409 response. No signed/public URL is generated.
        route = (
            "/storage/v1/object/authenticated/"
            if method == "GET"
            else "/storage/v1/object/"
        )
        url = (
            self.origin
            + route
            + quote(self.bucket, safe="")
            + "/"
            + quote(key, safe="/")
        )
        request = Request(
            url,
            data=payload,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "apikey": self.token,
                "Content-Type": "application/pdf",
                "x-upsert": "false",
            },
        )
        return build_opener(_NoRedirect()).open(request, timeout=25)

    def _assert_private_bucket(self) -> None:
        """Bucket naming is not an ACL: verify actual Supabase privacy."""
        url = self.origin + "/storage/v1/bucket/" + quote(self.bucket, safe="")
        request = Request(
            url,
            method="GET",
            headers={
                "Authorization": "Bearer " + self.token,
                "apikey": self.token,
            },
        )
        try:
            with build_opener(_NoRedirect()).open(request, timeout=15) as response:
                metadata = json.loads(response.read(8192))
        except (HTTPError, URLError, OSError, ValueError):
            raise RuntimeError("Cannot verify private OEM bucket") from None
        if not isinstance(metadata, dict) or metadata.get("public") is not False:
            raise PermissionError("OEM bucket must be explicitly private")

    def publish(self, manifest: OEMApproval, pdf: bytes) -> str:
        """Immutable PDF key; a 409 retry checks exact bytes, never overwrites."""
        if (
            not pdf.startswith(b"%PDF-")
            or len(pdf) > MAX_PDF_BYTES
            or hashlib.sha256(pdf).hexdigest() != manifest.pdf_sha256
        ):
            raise ValueError("private PDF differs from approved source")
        self._assert_private_bucket()
        try:
            with self._request(manifest.object_key, pdf, "POST") as response:
                response.read(1024)
        except HTTPError as error:
            if error.code != 409:
                raise RuntimeError("Private PDF upload refused") from None
            # An already-uploaded object is safe to reuse only if identical.
            try:
                with self._request(manifest.object_key, None, "GET") as response:
                    old = response.read(MAX_PDF_BYTES + 1)
                if hashlib.sha256(old).hexdigest() != manifest.pdf_sha256:
                    raise ValueError(
                        "private PDF object conflicts with approved source"
                    )
            except (HTTPError, URLError, OSError):
                raise RuntimeError("Unable to verify existing private PDF") from None
        except (URLError, OSError):
            raise RuntimeError("Private PDF upload unavailable") from None
        return manifest.object_key


class OEMKnowledgeRepository:
    """Atomically publish exact approved PDF metadata and reviewed text in Neon."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def publish(self, approval: OEMApproval, object_key: str) -> int:
        approval.assert_active()
        if object_key != approval.object_key:
            raise ValueError("PDF object key differs from approved source")
        ident = {"id": approval.document_id, "revision": approval.revision}
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))"),
                    {"id": approval.document_id},
                )
                existing = (
                    connection.execute(
                        text("""
                        SELECT d.source_sha256, d.source_object_key,
                               a.section_sha256, a.approval_reference
                        FROM capstone_knowledge.manual_documents AS d
                        JOIN capstone_knowledge.manual_approvals AS a
                        ON (a.document_id, a.revision)=(d.document_id, d.revision)
                        WHERE d.document_id=:id AND d.revision=:revision
                    """),
                        ident,
                    )
                    .mappings()
                    .first()
                )
                if existing is not None:
                    if (
                        existing["source_sha256"] != approval.pdf_sha256
                        or existing["source_object_key"] != object_key
                        or existing["section_sha256"] != approval.section_digest
                        or existing["approval_reference"] != approval.approval_reference
                    ):
                        raise ValueError("approved OEM revision cannot be overwritten")
                    count = connection.execute(
                        text("""
                            SELECT count(*) FROM capstone_knowledge.manual_sections
                            WHERE document_id=:id AND revision=:revision
                        """),
                        ident,
                    ).scalar_one()
                    if count != len(approval.sections):
                        raise ValueError("published OEM manual is incomplete")
                    return count
                connection.execute(
                    text("""
                        INSERT INTO capstone_knowledge.manual_documents
                            (document_id, revision, source_scope, title,
                             source_sha256, source_object_key,
                             approval_reference, is_published)
                        VALUES (:id, :revision, 'pilot', :title,
                                :pdf_sha, :object_key, :approval, FALSE)
                    """),
                    {
                        **ident,
                        "title": approval.title,
                        "pdf_sha": approval.pdf_sha256,
                        "object_key": object_key,
                        "approval": approval.approval_reference,
                    },
                )
                connection.execute(
                    text("""
                        INSERT INTO capstone_knowledge.manual_approvals
                            (document_id, revision, site_id, machine_id,
                             controller_family, controller_fingerprint,
                             approved_by, approval_reference, expires_at,
                             pdf_sha256, section_sha256, cloud_storage_approved,
                             retrieval_approved, embedding_egress_approved)
                        VALUES (:id, :revision, :site, :machine, :family,
                                :fingerprint, :approver, :approval, :expires,
                                :pdf_sha, :section_sha, TRUE, TRUE, :egress)
                    """),
                    {
                        **ident,
                        "site": approval.site_id,
                        "machine": approval.machine_id,
                        "family": approval.controller_family,
                        "fingerprint": approval.controller_fingerprint,
                        "approver": approval.approved_by,
                        "approval": approval.approval_reference,
                        "expires": approval.expires_at,
                        "pdf_sha": approval.pdf_sha256,
                        "section_sha": approval.section_digest,
                        "egress": approval.embedding_egress_approved,
                    },
                )
                for section in approval.sections:
                    connection.execute(
                        text("""
                            INSERT INTO capstone_knowledge.manual_sections
                                (document_id, revision, section_id, title,
                                 body, page_start, page_end,
                                 embedding_model, embedding)
                            VALUES (:id, :revision, :section, :title, :body,
                                    :start, :end, NULL, NULL)
                        """),
                        {
                            **ident,
                            "section": section.section_id,
                            "title": section.title,
                            "body": section.text,
                            "start": section.page_start,
                            "end": section.page_end,
                        },
                    )
                connection.execute(
                    text("""
                        UPDATE capstone_knowledge.manual_documents
                        SET is_published=FALSE
                        WHERE document_id=:id AND is_published=TRUE
                    """),
                    {"id": approval.document_id},
                )
                connection.execute(
                    text("""
                        UPDATE capstone_knowledge.manual_documents
                        SET is_published=TRUE
                        WHERE document_id=:id AND revision=:revision
                    """),
                    ident,
                )
        except SQLAlchemyError:
            raise RuntimeError("Neon OEM manual transaction failed") from None
        return len(approval.sections)


class ScopedOEMManualSearch:
    """Read-only, context-matched retrieval. No simulator or other-shop fallback."""

    def __init__(
        self,
        engine: Engine,
        *,
        site_id: str,
        machine_id: str,
        controller_family: str,
        controller_fingerprint: str,
    ):
        self.engine = engine
        self.identity = {
            "site": site_id,
            "machine": machine_id,
            "family": controller_family,
            "fingerprint": controller_fingerprint,
        }

    def search(self, query: str, *, limit: int) -> tuple[ManualSection, ...]:
        if not query.strip() or not 1 <= limit <= 5 or len(query) > 500:
            raise ValueError("OEM manual search query/limit invalid")
        try:
            with self.engine.connect() as connection:
                rows = (
                    connection.execute(
                        text("""
                        SELECT d.document_id, d.revision,
                               s.section_id, s.title, s.body
                        FROM capstone_knowledge.manual_documents d
                        JOIN capstone_knowledge.manual_approvals a
                          ON (a.document_id,a.revision)=(d.document_id,d.revision)
                        JOIN capstone_knowledge.manual_sections s
                          ON (s.document_id,s.revision)=(d.document_id,d.revision)
                        WHERE d.source_scope='pilot' AND d.is_published=TRUE
                          AND a.cloud_storage_approved=TRUE
                          AND a.retrieval_approved=TRUE
                          AND a.expires_at > now()
                          AND a.site_id=:site AND a.machine_id=:machine
                          AND a.controller_family=:family
                          AND a.controller_fingerprint=:fingerprint
                          AND to_tsvector('english', s.title || ' ' || s.body)
                              @@ plainto_tsquery('english', :query)
                        ORDER BY ts_rank_cd(
                            to_tsvector('english', s.title || ' ' || s.body),
                            plainto_tsquery('english', :query)
                        ) DESC, d.document_id, s.section_id
                        LIMIT :limit
                    """),
                        {**self.identity, "query": query, "limit": limit},
                    )
                    .mappings()
                    .all()
                )
        except SQLAlchemyError:
            raise RuntimeError("Approved OEM manual retrieval unavailable") from None
        return tuple(
            ManualSection(
                document_id=row["document_id"],
                revision=row["revision"],
                section_id=row["section_id"],
                title=row["title"],
                text=row["body"],
            )
            for row in rows
        )


def read_pdf(path: Path, approval: OEMApproval) -> bytes:
    """Read a bounded approved file, not its filename or untrusted metadata."""
    if not path.is_absolute() or refusal(path, "--source-pdf") is not None:
        raise ValueError("OEM source must be outside the public Git checkout")
    with path.open("rb") as source:
        pdf = source.read(MAX_PDF_BYTES + 1)
    if (
        len(pdf) > MAX_PDF_BYTES
        or not pdf.startswith(b"%PDF-")
        or hashlib.sha256(pdf).hexdigest() != approval.pdf_sha256
    ):
        raise ValueError("OEM PDF does not match authorized SHA-256")
    return pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly import an approved PDF and reviewed sections"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-pdf", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if (
        not args.manifest.is_absolute()
        or refusal(args.manifest, "--manifest") is not None
    ):
        parser.error("OEM approval manifest must be private and absolute")
    approval = OEMApproval.model_validate_json(args.manifest.read_bytes())
    approval.assert_active()
    pdf = read_pdf(args.source_pdf, approval)
    print(
        f"approved OEM source verified: {len(pdf)} bytes, "
        f"{len(approval.sections)} reviewed sections; document ID redacted"
    )
    if not args.apply:
        print("preview only: no Storage upload, Neon write or model egress")
        return 0
    origin = os.getenv("SUPABASE_STORAGE_URL", "")
    token = os.getenv("SUPABASE_STORAGE_SERVICE_KEY", "")
    bucket = os.getenv("SUPABASE_PRIVATE_OEM_BUCKET", "")
    storage = PrivatePDFStorage(origin=origin, token=token, bucket=bucket)
    manual = open_neon_manual()
    try:
        key = storage.publish(approval, pdf)
        written = OEMKnowledgeRepository(manual.engine).publish(approval, key)
        print(f"OEM manual published: {written} approved sections")
    finally:
        manual.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
