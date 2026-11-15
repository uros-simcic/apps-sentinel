# Apps Sentinel

A lightweight Python agent that checks application health
and proposes fixes for owner approval.

Under development. Monitoring and automated repairs are not enabled.

## Try the offline demo

Python 3.12 is tested in CI. No pip installation or credentials are needed.

```sh
python demo.py
python -m unittest discover -s tests -v
python scan.py validate --config config.example.json
```

The demo exercises the scanner with three synthetic workflow scenarios:
healthy, failed and unavailable. It makes no network requests.

## Current scope

Implemented: configuration validation, owner identity checks, read-only
GitHub access, workflow freshness checks, repository JSON checks and
a preview scan command.

A passing workflow does not prove the application works correctly.
JSON checks verify configured fields and output freshness; they do not
validate field types, value ranges or the deployed application's behavior.
Scheduling, proposal emails and repair execution are not implemented yet.

## Check application output

Add this check to an application's `checks` list, replacing the example
repository, file path and fields with those used by your application:

```json
{
  "id": "output",
  "kind": "repo_json",
  "repo": "example-owner/example-app",
  "path": "docs/now.json",
  "required_fields": ["temperature"],
  "timestamp_field": "measured_at",
  "max_age_hours": 2
}
```

The file is read from the repository's default branch.
Required fields must exist and must not be null. Nested fields use dots,
such as `weather.temperature`. The timestamp must include a timezone.
Stale output or missing values fail; unavailable evidence is unknown.
