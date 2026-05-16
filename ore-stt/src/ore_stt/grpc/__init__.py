"""gRPC layer for ore-stt.

protoc-generated stubs live in ``./generated`` and import one another with
package-root-relative paths (``from ore.stt.v1 import stt_pb2``). Put that
directory on ``sys.path`` so those imports resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

_GENERATED = Path(__file__).parent / "generated"
if _GENERATED.is_dir() and str(_GENERATED) not in sys.path:
    sys.path.insert(0, str(_GENERATED))
