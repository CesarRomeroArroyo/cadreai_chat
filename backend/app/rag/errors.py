class IngestionError(ValueError):
    """Expected source ingestion failure safe to show to an administrator."""


class UnsupportedDocumentError(IngestionError):
    pass


class EmptyDocumentError(IngestionError):
    pass


class TextlessPdfError(IngestionError):
    pass


class UnsafeUrlError(IngestionError):
    pass


class DownloadError(IngestionError):
    pass


class IndexCompatibilityError(RuntimeError):
    pass
