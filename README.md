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
GitHub access, workflow freshness checks and a preview scan command.

A passing workflow does not prove the application works correctly.
Functional checks, scheduling, proposal emails and repair execution
are not implemented yet.
