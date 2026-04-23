# app/extraction/learning_outcomes_parser.py
"""
Parses Course_Learning_Outcomes_OneRowPerCourse.csv and merges learning outcomes
into ParsedData.csv, matching on course_code.
"""
from __future__ import annotations

import csv
import os
from typing import Dict, List, Optional


def load_learning_outcomes(csv_path: str) -> Dict[str, str]:
    """
    Load learning outcomes CSV into a dict: course_code -> learning_outcomes string.
    """
    outcomes: Dict[str, str] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("course_code", "").strip()
            lo = row.get("learning_outcomes", "").strip()
            if code:
                outcomes[code] = lo
    return outcomes


def merge_outcomes_into_parsed_data(
    parsed_data_path: str,
    outcomes_csv_path: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Merge learning outcomes into ParsedData.csv.

    Args:
        parsed_data_path: Path to ParsedData.csv
        outcomes_csv_path: Path to Course_Learning_Outcomes_OneRowPerCourse.csv
        output_path: Output path (defaults to overwriting parsed_data_path)

    Returns:
        Path to the output file
    """
    if output_path is None:
        output_path = parsed_data_path

    outcomes = load_learning_outcomes(outcomes_csv_path)

    rows: List[Dict[str, str]] = []
    fieldnames: List[str] = []

    with open(parsed_data_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])

        if "learning_outcomes" not in fieldnames:
            fieldnames.append("learning_outcomes")

        for row in reader:
            code = row.get("course_code", "").strip()
            row["learning_outcomes"] = outcomes.get(code, "")
            rows.append(row)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for r in rows if r.get("learning_outcomes"))
    print(f"Merged learning outcomes: {matched}/{len(rows)} courses matched")

    return output_path


def parse_outcomes_to_list(outcomes_str: str) -> List[str]:
    """
    Parse the comma-separated learning outcomes string into a list.
    Handles outcomes that may contain commas by splitting on '., ' pattern.
    """
    if not outcomes_str:
        return []
    parts = outcomes_str.split("., ")
    return [p.strip().rstrip(".") + "." for p in parts if p.strip()]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Merge learning outcomes into ParsedData.csv")
    parser.add_argument(
        "--parsed-data",
        default="Data/Processed/ParsedData.csv",
        help="Path to ParsedData.csv",
    )
    parser.add_argument(
        "--outcomes",
        default="Data/Raw/Inputs/Course_Learning_Outcomes_OneRowPerCourse.csv",
        help="Path to learning outcomes CSV",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (defaults to overwriting parsed-data)",
    )

    args = parser.parse_args()

    output = merge_outcomes_into_parsed_data(
        args.parsed_data,
        args.outcomes,
        args.output,
    )
    print(f"Output written to: {output}")
