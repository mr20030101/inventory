"""Entry point used by PyInstaller and for running from source: python run.py"""
import sys

from inventory_app.app import main

if __name__ == "__main__":
    sys.exit(main())
