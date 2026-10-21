"""
JIRVA - Calibration Data Loader
--------------------------------------
Shared CSV loader for the hand-labeled calibration logs (logs/*.csv)
produced during Day 5/9 calibration. Used by both the pytest regression
suite (tests/conftest.py) and the evaluation module (evaluation.py), so
there's a single definition of "how to read a calibration log" rather than
two copies drifting apart.
"""
import csv
import os

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")


def load_calibration_csv(filename):
    """Reads a calibration log from logs/ and returns a list of dict rows
    (all values as strings, as csv.DictReader returns them - callers convert
    numeric fields themselves since some calibration logs mix types)."""
    path = os.path.join(LOGS_DIR, filename)
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows
