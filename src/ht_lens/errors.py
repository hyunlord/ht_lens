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
