import csv
from django.http import StreamingHttpResponse


class CSVRenderer:
    def __init__(self, filename="report.csv"):
        self.filename = filename

    def render(self, headers, rows):
        pseudo_buffer = PseudoBuffer()
        writer = csv.writer(pseudo_buffer)
        # Plain utf-8: with charset=utf-8-sig Django's encoder prepends a BOM
        # to EVERY streamed chunk (one per row). The single Excel-detection BOM
        # is yielded explicitly by _iter instead.
        response = StreamingHttpResponse(
            streaming_content=self._iter(writer, headers, rows),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = f'attachment; filename="{self.filename}"'
        return response

    def _iter(self, writer, headers, rows):
        yield "\ufeff"
        yield ",".join(headers) + "\n"
        for row in rows:
            sanitized = [str(cell).replace(",", "،").replace("\n", " ") for cell in row]
            yield ",".join(sanitized) + "\n"


class PseudoBuffer:
    def write(self, value):
        return value


class Echo:
    def write(self, value):
        return value
