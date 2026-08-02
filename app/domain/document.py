from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_id: str
    title: str
    content: str
    source: str


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    document_type: str
    title: str
    original_filename: str
    content_type: str
    s3_object_key: str
    s3_version_id: str
    status: str
    document_id: int | None = None
    category: str | None = None
    source_url: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
