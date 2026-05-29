"""Domain errors with CLI exit-code mapping."""


class HtLensError(Exception):
    """Base class for ht_lens domain errors."""

    exit_code: int = 1


class EncryptedPDFError(HtLensError):
    exit_code = 2


class CorruptedPDFError(HtLensError):
    exit_code = 3


class OutputDirNotEmptyError(HtLensError):
    exit_code = 2


class IngestError(HtLensError):
    """Raised when an extract directory cannot be ingested."""

    exit_code = 2


class DocumentAlreadyIngested(IngestError):
    """Raised when a document with the same filename already exists in DB and
    ``--overwrite`` was not passed."""

    exit_code = 2


class SchemaVersionMismatch(HtLensError):
    """Raised when DB schema version is missing or older than the code head."""

    exit_code = 3


class MineruError(HtLensError):
    """Raised when the MinerU extraction subprocess fails or its output is
    unusable (Phase 8a). Covers missing binary, nonzero exit, timeout, and
    absent/empty ``content_list.json``."""

    exit_code = 4
