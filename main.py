"""Startpunkt: grafische Oberfläche."""
import sys


def main() -> None:
    try:
        from aki_data.gui import run
    except ImportError:
        sys.exit("Tkinter ist nicht installiert – bitte Python mit Tkinter installieren.")
    run()


if __name__ == "__main__":
    main()
