# Deployment to Dewacloud

`.github/workflows/deploy.yml` deploys the ASGI API and the web application to
the Dewacloud node over SSH. It runs automatically on every push to `main` and
can be triggered manually for a re-deploy or rollback.

## Current status

The pipeline is complete but **not yet functional**, by design. The runtime
modules (`src/alamatin/api.py`, `contracts/`, the quality gate, the validator,
the normalizer) still live only in the internal repository, and `web/` here
holds a placeholder README. The `verify` job checks for
`src/alamatin/api.py` and `contracts/address-api.v1.schema.json` and fails with
an explicit message when they are absent, so a push cannot quietly deploy an
empty skeleton. Deploys begin working once that code is synced here.

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
