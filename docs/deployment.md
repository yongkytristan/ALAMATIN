# Deployment

The production deployment is automated by
`.github/workflows/deploy.yml`. Every push to `main` first runs repository
validation and the complete Python test suite. A release is uploaded and
activated only after those checks pass.

## Public endpoints

- Application: <https://alamatin.flow-app.my.id>
- Health check: <https://alamatin.flow-app.my.id/api/health>

The health endpoint must return HTTP 200 with `status: healthy` and a ready
pipeline dependency. The application endpoint is also recorded as the GitHub
Actions production environment URL.

## Release flow

1. Validate tracked files and repository policy.
2. Run the complete Python test suite.
3. Verify the locked dependencies for Python 3.11.
4. Build a minimal payload containing the runtime, API contract, web app, and
   approved runtime reference.
5. Upload the payload to a versioned release directory.
6. Activate the release atomically, restart the service, and retain prior
   releases for rollback.
7. Probe the public health endpoint and fail the workflow if it does not return
   HTTP 200.

The workflow never commits connection details or credentials. Deployment
configuration is stored in GitHub Actions secrets and variables.

## Required GitHub Actions configuration

The following secret names are required. Their values are maintained by the
deployment administrator and are intentionally not documented in this public
repository.

| Secret | Purpose |
|---|---|
| `DEWACLOUD_SSH_HOST` | Deployment gateway hostname |
| `DEWACLOUD_SSH_USER` | Deployment account identifier |
| `DEWACLOUD_SSH_PORT` | Deployment gateway port |
| `DEWACLOUD_SSH_KEY` | Dedicated private deployment key |
| `DEWACLOUD_SSH_KNOWN_HOSTS` | Pinned SSH host key |
| `DEWACLOUD_RESTART_COMMAND` | Optional service restart command |

The non-sensitive repository variables are:

| Variable | Public value or purpose |
|---|---|
| `DEWACLOUD_APP_URL` | `https://alamatin.flow-app.my.id` |
| `DEWACLOUD_HEALTH_URL` | `https://alamatin.flow-app.my.id/api/health` |
| `DEWACLOUD_REMOTE_ROOT` | Optional provider-specific release root |
| `DEWACLOUD_PYTHON` | Optional Python interpreter override |

Connection values must be entered directly through repository settings. Never
paste them into an issue, pull request, workflow, example command, or test
fixture.

## Deployment payload

The payload deliberately excludes tests, documentation, experiment artifacts,
notebooks, local environments, caches, and private or raw datasets. The one
governed reference required by the running pipeline is copied explicitly rather
than including the full `data/` tree.

The activation script is `scripts/deploy/activate_release.sh`. It verifies the
interpreter, installs the hashed dependency lock, switches the active release,
and prunes old releases only after activation succeeds.

## Rollback

Use the workflow's manual `release_ref` input with a previously verified commit
or tag. The same validation steps run before rollback, and the previous release
remains available if upload, installation, activation, or health verification
fails.

Operational hostnames, account identifiers, provider console instructions, and
key-registration procedures are intentionally maintained outside this public
repository.
