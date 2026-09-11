# DigitalOcean deployment runbook

This deployment keeps releases immutable and runtime data separate. It does not use Docker, MySQL, Redis, PM2, or public application ports.

## Layout

```text
/opt/cadre-ai/releases/<revision>/  immutable application release
/opt/cadre-ai/current               active release symlink
/opt/cadre-ai/previous              rollback release symlink
/opt/cadre-ai/tools                 isolated deployment tools
/opt/cadre-ai/python                isolated CPython 3.12
/opt/cadre-ai/bin/rollback          atomic rollback command
/var/lib/cadre-ai/index             persistent RAG index
/var/lib/cadre-ai/models            persistent model cache
/etc/cadre-ai/backend.env           production environment, mode 0640
/etc/nginx/sites-available/cadre-ai isolated Nginx site
```

## Deployment sequence

1. Build and test frontend/backend locally.
2. Package frontend `dist` plus backend source, `pyproject.toml`, and `uv.lock` into a revision-named archive.
3. Upload archive and templates to a temporary host path.
4. Create a dedicated `cadreai` service account and application directories if absent.
5. Install `uv` and CPython 3.12 under `/opt/cadre-ai`; do not change system Python.
6. Extract a new immutable release and run `uv sync --frozen --no-dev` inside its backend directory.
7. Smoke-test the release on an unused temporary localhost port.
8. Preserve the old `current` target as `previous`, then atomically switch `current`.
9. Install and validate the systemd unit and isolated Nginx site before reload.
10. Request or reuse the hostname certificate with Certbot, then verify HTTPS.

Never overwrite an existing release. Never edit unrelated Nginx sites or services.

## Release rollback

After at least two releases exist:

```bash
sudo /opt/cadre-ai/bin/rollback
```

The command swaps `current` and `previous`, restarts the API, waits up to 60 seconds for local health while the embedding model loads, and automatically restores the original release if the rollback target fails.

## First-deployment removal

No previous application release exists after the first deployment. To remove only Cadre AI routing and runtime while retaining recoverable data:

```bash
sudo systemctl disable --now cadre-ai.service
sudo rm /etc/systemd/system/cadre-ai.service
sudo systemctl daemon-reload
sudo rm /etc/nginx/sites-enabled/cadre-ai
sudo rm /etc/nginx/sites-available/cadre-ai
sudo nginx -t
sudo systemctl reload nginx
sudo rm /opt/cadre-ai/current
```

This intentionally preserves `/opt/cadre-ai/releases`, `/var/lib/cadre-ai`, `/etc/cadre-ai/backend.env`, and issued certificates. Review those paths manually before permanent deletion.
