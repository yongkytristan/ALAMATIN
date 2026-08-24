# Deployment to Dewacloud

`.github/workflows/deploy.yml` deploys the ASGI API and the web application to
the Dewacloud node over SSH. It runs automatically on every push to `main` and
can be triggered manually for a re-deploy or rollback.

Public endpoints:

- Application: <https://alamatin.flow-app.my.id>
- Health check: <https://alamatin.flow-app.my.id/api/health>

## Current status

The runtime code is now present: the API, contracts, quality gate, validator,
normalizer, and PII redaction have been synced from the internal repository, so
the `verify` job's deployability guard passes and a deploy can proceed.

The ASGI server is now pinned: `uvicorn==0.52.4` with hashes in
`requirements.lock`, recorded as DEC-005 in
[`decision-log.md`](decision-log.md). The service entrypoint is
`alamatin.service:app` (see [`integration.md`](integration.md); `alamatin.api:app`
is the transport with unconfigured handlers and answers `503` by design). Verified end to end on the node: the lock installs under
`pip install --require-hashes` and `uvicorn 0.52.4` runs on CPython 3.11.13.
The `verify` job also resolves the lock for the deploy target's interpreter and
platform, so a bad pin or missing hash fails a check rather than a deploy.

Two things still block a *useful* deploy:

1. **The deploy key is not registered yet.** See "Registering the deploy key"
   below — this must be done through the Dewacloud dashboard.

2. ~~**The default `app` has no pipeline wired.**~~ Resolved by ALM-028. The
   service entrypoint is now **`alamatin.service:app`**, which wires the real
   pipeline; `/health` returns `200 healthy`. A deployment still serving
   `alamatin.api:app` will keep answering `503`, so update the systemd unit's
   `ExecStart` accordingly and only then set `DEWACLOUD_HEALTH_URL`.
   See [`integration.md`](integration.md).

   Historic note, kept because it explains the `503` in earlier runs:
   `create_app()` defaults to an
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

## The target node

Surveyed directly over SSH on 22 August 2026:

| Property | Value |
|---|---|
| OS | AlmaLinux 9.7 |
| Login | `root`, home `/root` |
| System Python | 3.9.25 (`/usr/bin/python3`) — **cannot run this codebase** |
| Deploy interpreter | `python3.11` (3.11.13) — installed 22 August 2026 |
| ASGI server | none preinstalled; supplied per release from `requirements.lock` |
| Supervision | `systemctl` and `jem` present; `supervisorctl` absent |
| Disk | 449 GB free |

### The node's Python is too old

This codebase uses `dataclass(slots=True)` in `api.py`, `quality_gate.py`,
`administrative_validator.py`, and `address_normalizer.py`. That parameter is
Python 3.10+, and the node's `python3` is 3.9:

```
python3 (Python 3.9.25) -> dataclass() got an unexpected keyword argument 'slots'
```

So `activate_release.sh` defaults to `python3.11` rather than `python3`, and
refuses to continue if the chosen interpreter is missing or too old. It reports
the reason instead of letting the service crash on import after a deploy that
claimed success. It also rebuilds the shared virtualenv if it finds one built
from a different Python version, so a bad environment cannot survive later
deploys.

This has already been done on the current node. On a rebuilt or replacement
node, install it again:

```bash
dnf install -y python3.11
```

Override the default with the `DEWACLOUD_PYTHON` repository variable if a
different interpreter is preferred.

### Registering the deploy key

**`ssh-copy-id` does not work here.** The Dewacloud SSH gateway
(`SSH-2.0-JSSHProxy`) authenticates against the SSH keys registered on the
*account*, not against the container's `~/.ssh/authorized_keys`. Running
`ssh-copy-id` reports `Number of key(s) added: 1` and appends to
`authorized_keys`, but the gateway never reads that file and the key is still
refused:

```
debug1: Offering public key: alamatin_deploy ED25519 ...
79503-9371@gate.infra.dewacloud.com: Permission denied (publickey,...).
```

Add the deploy key through the Dewacloud dashboard's SSH key settings instead,
then verify with:

```bash
ssh -i ~/.ssh/alamatin_deploy -o IdentitiesOnly=yes -p 3022 \
  79503-9371@gate.infra.dewacloud.com "echo OK"
```

`IdentitiesOnly=yes` matters: without it, ssh may silently succeed using a
different key from your agent and hide the fact that the deploy key itself is
not authorised.

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
| `DEWACLOUD_HEALTH_URL` | `https://alamatin.flow-app.my.id/api/health` | Full public health-check URL. When unset, the post-deploy health check is skipped. |
| `DEWACLOUD_APP_URL` | `https://alamatin.flow-app.my.id` | Shown as the deployment URL on the GitHub run. |

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
