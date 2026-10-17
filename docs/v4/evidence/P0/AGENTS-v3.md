# Project guidance

Read README.md and docs/CLOUD_DEVELOPMENT.md before changing runtime configuration.

## Current baseline

- main.py is the Core v3 FastAPI entrypoint. PostgreSQL is the only authority and LangGraph executes ConsultationService for web, tarot, channels and reports.
- Legacy SQLite/JSON readers are migration-only. Old ChatAgent and global Hermes sessions must never be imported by a production entrypoint.
- Keep professional chart/card details in the final expandable appendix. Lead with a readable answer and practical reasoning. Separate user facts, preferences, unknowns and symbolic interpretations.
- Preserve frozen tarot draws, source authorization, revisions, correction/deletion rules and scoped ownership.

## Development

Use isolated synthetic data under private/ and process environment variables. main.py does not load .env automatically. Never commit production credentials, user records, uploads, databases or backups.

Run the checks appropriate to the change:

```bash
python -m unittest discover -s tests -p 'test_core*.py'
npm test
node tests/dom.test.cjs
node --check static/app.js
npm run build
```

Core integration tests require an isolated PostgreSQL database and substitute only models or external transmission. Set CORE_TEST_DSN and CHART_PYTHON explicitly. Legacy behavior migration is recorded in docs/CORE_V3_BEHAVIOR_COVERAGE.json. Missing dependencies or skipped tests are not evidence of chart accuracy. Do not convert a successful schema check into a claim of verified life prediction.

Do not deploy to production, run real messaging/report delivery, copy production data or modify cron/service settings as part of ordinary development. Those are separate release actions. The daily schedule is Asia/Shanghai, preparation at 06:45 and delivery at 07:00.

Prefer small, reviewable changes. Record behavior, validation and remaining limitations in the relevant documentation. Keep generated Tailwind styles consistent with the source when styles change.
