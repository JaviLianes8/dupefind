"""Allow ``python -m dupefind``."""

import sys

from ._cli import main

sys.exit(main())
