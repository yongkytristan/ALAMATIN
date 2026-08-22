# Deployment to Dewacloud

`.github/workflows/deploy.yml` deploys the ASGI API and the web application to
the Dewacloud node over SSH. It runs automatically on every push to `main` and
can be triggered manually for a re-deploy or rollback.

## Current status

The runtime code is now present: the API, contracts, quality gate, validator,
normalizer, and PII redaction have been synced from the internal repository, so
the `verify` job's deployability guard passes and a deploy can proceed.

Two things still block a *useful* deploy, and both are outside this pipeline:

1. **No ASGI server is declared.** `requirements.lock` still declares no
   dependencies. `src/alamatin/api.py` is a dependency-free ASGI application,
   but something has to serve it. The service entrypoint is
   `alamatin.api:app`, for example `uvicorn alamatin.api:app`. Adding the
   server to the lock file is a stack decision that must be recorded first,
   per this repository's dependency policy, and the lock file must carry
   hashes because the activation script installs with `--require-hashes`.

2. **The default `app` has no pipeline wired.** `create_app()` defaults to an
   unconfigured parse/validate handler and an unconfigured dependency probe.
   Verified against the synced tree with a real Uvicorn run:

   ```
   GET  /health              -> 503  status=degraded  app=alive
   POST /parse               -> 503  PIPELINE_UNAVAILABLE
   POST /parse (bad json)    -> 400  INVALID_JSON
   ```

   This is correct behaviour, not a bug: the app is alive and reports honestly
   that a critical dependency is missing. But it means **`/health` will return
   `503` until real handlers are wired**, so leave `DEWACLOUD_HEALTH_URL`
   unset for now. The deploy skips the health check when it is unset; setting
   it too early would fail every deploy for the wrong reason.

## What the pipeline does

1. **verify** — runs `scripts/check_repository.py` and the full test suite
   against the exact commit being deployed, then confirms a deployable
   application is present. A red `main` never reaches the server.
2. **deploy** — builds a payload containing only `src/`, `contracts/`,
   `web/`, `requirements.lock`, and the activation script; tests, docs, and the
   governed `data/` directories are excluded.
3. Uploads the payload to `RELEASE_ROOT/releases/<timestamp>-<sha>/` with
   `rsync` over SSH.
4. Runs `scripts/deploy/activate_release.sh` on the node: installs locked
   dependencies into a shared virtualenv, swaps the `current` symlink
   atomically, restarts the service, and prunes all but the five most recent
   releases.
5. Probes the health endpoint and fails the run if it never returns `200`.

Because releases are unpacked side by side and activated by a symlink swap, a
failed upload or a failed dependency install leaves the previous release
serving traffic untouched.

## Required repository secrets

Set these in **Settings → Secrets and variables → Actions → Secrets**. None of
them may be committed: this repository is public.

| Secret | Value | Notes |
|---|---|---|
| `DEWACLOUD_SSH_HOST` | `gate.infra.dewacloud.com` | The SSH gateway host. |
| `DEWACLOUD_SSH_USER` | e.g. `79503-9371` | The Dewacloud environment/node user. |
| `DEWACLOUD_SSH_PORT` | `3022` | Dewacloud does not use port 22. |
| `DEWACLOUD_SSH_KEY` | private key, full PEM | Deploy key. Paste the entire file including the `BEGIN`/`END` lines. |
| `DEWACLOUD_SSH_KNOWN_HOSTS` | pinned host key line(s) | See below. Required. |
| `DEWACLOUD_RESTART_COMMAND` | command to restart the service | Optional but strongly recommended; see below. |

Host and user are kept as secrets rather than plain variables so the target can
be rotated without a commit, and so a fork cannot read the infrastructure
address out of the workflow file.

### Generating the SSH key

Generate a dedicated key for CI rather than reusing a personal one, so it can be
revoked on its own:

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f alamatin_deploy -N ""
```

Add `alamatin_deploy.pub` to the node's `~/.ssh/authorized_keys` (Jason, or the
Dewacloud dashboard's SSH access panel), and paste the contents of the private
key `alamatin_deploy` into `DEWACLOUD_SSH_KEY`.

### Generating `DEWACLOUD_SSH_KNOWN_HOSTS`

The workflow uses `StrictHostKeyChecking=yes` with a pinned host key. It does
not run `ssh-keyscan` at deploy time on purpose: trusting whatever key the host
presents during a deploy would hand the deploy key to anyone able to intercept
the connection.

Run this **once, from a trusted network**, and verify the fingerprint against
the Dewacloud dashboard before saving it:

```bash
ssh-keyscan -p 3022 gate.infra.dewacloud.com
```

Paste the full output into `DEWACLOUD_SSH_KNOWN_HOSTS`.

### Choosing a restart command

This depends on how the service is supervised on the node, which is Jason's
side of the work. Common shapes:

```bash
# systemd, if the node grants the deploy user permission
sudo systemctl restart alamatin

# a supervised process manager
supervisorctl restart alamatin

# Jelastic/Dewacloud application server restart hook
jem service restart
```

If `DEWACLOUD_RESTART_COMMAND` is left unset, the deploy still uploads and
activates the release but logs a warning that the running process was not
restarted — the new code will be on disk without being live. This is a warning
rather than a failure so the pipeline can be validated before the service
supervision is finalised.

## Optional repository variables

Set these in **Settings → Secrets and variables → Actions → Variables**. They
are not sensitive.

| Variable | Default | Purpose |
|---|---|---|
| `DEWACLOUD_REMOTE_ROOT` | `/home/jelastic/alamatin` | Deploy root on the node. Override if the account uses a different home. |
| `DEWACLOUD_HEALTH_URL` | unset | Full URL of `GET /health`. When unset, the post-deploy health check is skipped. |
| `DEWACLOUD_APP_URL` | unset | Shown as the deployment URL on the GitHub run. |

The health check treats `503` as a distinct, reported outcome rather than a
generic timeout, because the API returns `503` with `app: alive` when the
process is up but a critical dependency is failing. That distinction is the
whole point of the health contract, so the deploy log preserves it.

## Rollback

Re-run the workflow from the Actions tab with `release_ref` set to the last
known good commit SHA or tag. The `verify` job runs against that commit, so a
rollback is checked in exactly the same way as a forward deploy.

If GitHub itself is unavailable, the previous releases are still on the node:
point `$DEWACLOUD_REMOTE_ROOT/current` at the previous entry under
`releases/` and restart the service.

## Hardening still open

- `requirements.lock` currently declares no dependencies. Once the runtime
  stack is added, the activation script installs it with `--require-hashes`, so
  the lock file must carry hashes. A lock file without hashes will fail the
  deploy rather than install unverified packages.
- The `production` environment has no required reviewers yet. Adding them in
  repository settings turns every deploy into an explicit human approval, which
  is worth considering before the submission freeze.
