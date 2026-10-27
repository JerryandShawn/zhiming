"""Export a fresh synthetic course directory from the pinned meta v5 delivery."""

from __future__ import annotations

import argparse
import json

from course_bundle import ERROR, load_bundle
from course_projection import WEB, export_course


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="test-results/course-v5")
    arguments = parser.parse_args()
    try:
        values, hashes = load_bundle()
        manifest = export_course(WEB / arguments.output, values, hashes)
    except (ValueError, OSError):
        raise SystemExit(ERROR) from None
    print(
        json.dumps(
            {
                "status": "exported",
                "lessons": manifest["lessons"],
                "quizzes": manifest["quizzes"],
                "model_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
