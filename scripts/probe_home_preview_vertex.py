"""Opt-in provider smoke check, sanitized output only, no publication or DB writes."""

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values

from app.core.config import Settings
from app.services.home_preview_vertex import VertexPreviewProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    values = dotenv_values(args.env_file)
    settings = Settings(
        _env_file=None,
        google_cloud_project=values.get("GOOGLE_CLOUD_PROJECT"),
        google_application_credentials_json=values.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"),
    )
    provider = VertexPreviewProvider(settings)
    payload = json.loads(Path(args.snapshot).read_text())
    report = {
        "model": settings.home_preview_vertex_model,
        "location": settings.home_preview_vertex_location,
    }
    try:
        analysis, usage = provider.analysis(payload)
        report.update(state="success", analysis=analysis, usage=usage)
    except Exception as exc:  # noqa: BLE001 - audit reports only a sanitized error type
        report.update(state="failed", error_type=type(exc).__name__)
        if hasattr(exc, "response"):
            report["http_status"] = exc.response.status_code
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "analysis"}))


if __name__ == "__main__":
    main()
