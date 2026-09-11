import re
import uuid
from collections.abc import Mapping

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def request_id_from_headers(headers: Mapping[str, str]) -> str:
    candidate = headers.get("x-request-id", "")
    return candidate if REQUEST_ID_RE.fullmatch(candidate) else uuid.uuid4().hex
