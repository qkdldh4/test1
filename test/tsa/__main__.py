"""``python -m tsa`` 로 로컬 서버를 실행하는 단축 진입점."""

from __future__ import annotations

import sys

from .server import main

if __name__ == "__main__":
    sys.exit(main())
