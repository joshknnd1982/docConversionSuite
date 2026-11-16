"""Allow `python -m pdfmd` to run the command-line interface."""
from .cli import main

raise SystemExit(main())
