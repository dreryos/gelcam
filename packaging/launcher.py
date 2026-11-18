"""PyInstaller entry point (the package uses relative imports, so it cannot be run as a script itself)."""

from gelcam.__main__ import main

raise SystemExit(main())
