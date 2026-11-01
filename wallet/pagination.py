from rest_framework.pagination import CursorPagination


class LedgerEntryCursorPagination(CursorPagination):
    """Newest first, stable under concurrent inserts, index friendly."""

    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = "-id"
