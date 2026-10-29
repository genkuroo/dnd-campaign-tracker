# Plan: a real dev → test → staging → prod pipeline

**Status: both halves built (2026-10-19).** Test suite, staging environment,
auto-deploy-to-staging, and the manual promote-to-prod workflow are all in
place. What's left is step 6 — one full real cycle end to end, to prove the
whole pipeline before trusting it for real work. Written 2026-09-30, after
verifying the project's actual current state directly (see below) rather than
trusting older notes about it.

## Why

Everything else in this repo has been built solo, deployed by hand
(`fly deploy`, now really `git pull` + `docker compose up -d --build` on the
Pi — see below), straight to the one production instance real players use.
That's fine for a personal project, but it's the opposite of how a real team
ships changes: develop a feature, prove it works somewhere live that isn't
production, then deliberately promote it. The goal here is to build that real
workflow against this actual, actively-used app — not a toy — so the practice
is real practice, not a simulation.

## Ground truth, verified 2026-09-30 (don't trust older notes without re-checking)

- **Production is the Raspberry Pi, not Fly.io.** `dnd.gen-kuro.com` is live
  and healthy (`homelab-pi`'s `docker-compose.yml`, service `dnd`, built
  straight from this repo). The original `dnd-campaign-tracker.fly.dev` Fly
  app is dead — DNS still resolves and Fly's edge still accepts a TCP
  connection, but the TLS handshake fails outright (`SSL_ERROR_SYSCALL`),
  meaning there's no running machine behind it anymore. `fly.toml` and the
  Fly-specific deploy docs in this repo are now historical, not current —
  worth a cleanup pass at some point so they stop being misleading.
- **Deploys today are entirely manual**, on the Pi: `git pull` in
  `/opt/homelab`, then `docker compose up -d --build dnd` (per `homelab-pi`'s
  own conventions — never a bare `docker compose up -d` there, since that
  would also touch `sleeper-bot`).
- **Zero automated tests exist.** The `test_*.db` files in this repo are
  SQLite databases, not test code. There is currently nothing for a pipeline
  to actually gate on.
- **The project's own `CLAUDE.md` convention is "commit directly to main, no
  branches."** The plan below is designed to not fight that — no feature
  branches required, see below.
- **Backup status** (relevant since "prod" here means real player data):
  `dnd`'s Docker volume *is* covered by the Pi's nightly local backup
  (`backup.sh`, 14-day retention, same SD card as the live data). It is
  *not* covered by the off-site R2 sync (`r2-sync.sh` is hardcoded to
  `ffta-*.db.gz` only). Worth fixing independently of this plan — a card
  failure currently takes out the live data and all local backups at once.

## The model: mirror what already worked on `url-shortener-k8s`

No feature branches needed. Instead: **`main` continuously deploys to
staging automatically; promotion to prod is a separate, deliberate, manual
step.** You still commit straight to `main`, same as always — but now that
commit has to prove itself live on staging before you choose to promote it.
This is the same shape as that project's `deploy-dev` (automatic, every push)
vs. `promote.yml` (manual `workflow_dispatch`).

## What needs to be built

1. ~~**A real (if small) automated test suite.**~~ **Done (2026-10-05).** 27
   pytest tests in `tests/` — `requirements-dev.txt` + `pytest`. Covers
   login/setup/registration, the visibility spine (DM-sees-everything vs.
   player-sees-revealed-only, view vs. edit, 404-not-403 for hidden), character
   creation (DM authoring vs. player self-service), and combat basics
   (snapshot-on-add independence, initiative, damage, DM-only gating). Each
   test runs against its own throwaway SQLite file via `DND_DB_PATH`. Verified
   the suite has teeth, not just green checkmarks, by deliberately breaking
   `can_view_creature` and confirming the right test failed, then reverting.
   Not exhaustive by design (no spellcasting/inventory/world-layer coverage
   yet) — enough to give the pipeline below something genuine to gate on.
2. ~~**A staging environment.**~~ **Done (2026-10-09).** Went with Option A
   below (a second container on the Pi) after confirming real headroom —
   see the "Open decisions" entry for the verification detail. The other
   two options were considered but not built:

   | Option | Cost | Notes |
   |---|---|---|
   | A second container on the same Pi (`dnd-staging` service in `homelab-pi`'s compose file, own subdomain, own volume seeded with fake campaign data) — **chosen** | Free | Consistent with the rest of the homelab's self-hosted philosophy. Shares the Pi's limited resources and shares its fate — if the Pi goes down, staging does too. |
   | A small environment elsewhere (e.g. Fly.io's free tier, now used purely as disposable staging rather than as prod) | Likely free at this scale | Doesn't compete with the Pi's resources. Mirrors a real, common pattern: durable prod on owned hardware, disposable staging in the cloud. |
   | Local-only testing (Docker Compose on a dev machine) before deploying straight to the Pi | Free | Simplest, but not a "real live pre-prod environment" — weaker simulation of the actual workflow this plan exists to practice. |

3. **Two GitHub Actions workflows**, same shape as `url-shortener-k8s`:
   - ~~On every push to `main`: run the test suite, then... deploy to staging
     automatically.~~ **Done (2026-10-13).** `.github/workflows/deploy-staging.yml`:
     runs pytest, and on success, joins the tailnet (ephemeral, scoped to
     `tag:ci-deploy`) and SSHes into the Pi with a key restricted
     server-side (`authorized_keys` forced command) to running exactly one
     script — `homelab-pi/scripts/deploy-staging.sh` — and nothing else.
     Verified end-to-end for real multiple times, including confirming zero
     impact on `dnd`/`stocks`/`fitness`/`fantasy` after each deploy.
   - ~~A separate, manual `workflow_dispatch` workflow: promotes the exact
     tested commit to prod.~~ **Done (2026-10-19).**
     `.github/workflows/promote-prod.yml`: manual-trigger only, runs pytest,
     then a `production` GitHub Environment (you as required reviewer) gates
     the deploy job — nothing touches the Pi until that approval lands. The
     deploy step reuses the staging mechanism exactly (tailnet join, SSH to
     a forced-command key), pointed at `dnd` instead of `dnd-staging`, via a
     separate key (`github-actions-deploy-prod`) stored as an
     environment-scoped secret so it's only ever reachable post-approval.
     `homelab-pi/scripts/deploy-prod.sh` is the forced command on the Pi
     side. **Gotcha hit building this:** the `authorized_keys` forced-command
     syntax (`command="...",no-pty,...`) needs the quotes — appending the
     line through a nested SSH call let the shell strip them, which didn't
     error, it just made sshd silently fail to parse that one line and fall
     through to password auth (which then correctly failed). Caught by
     testing the new key end-to-end with `-o IdentitiesOnly=yes` (without it,
     the admin's own agent-loaded key silently covered for the broken one,
     masking the bug) before trusting it in CI.

## Open decisions

- [x] **Which staging option — Option A, a second container on the Pi.**
      Resolved 2026-10-05: checked the Pi directly over SSH. 2.7GB RAM free,
      and while `df` showed only 4.7GB disk free, 2.2GB of that is reclaimable
      Docker build cache, not real usage — the `dnd` volume itself is 700KB
      and the container runs near-0% CPU at idle. Same pattern as the existing
      `stock-demo`/`fitness-demo` sibling services.
- [x] **Scope of the initial test suite — resolved 2026-10-05,** see above.
- [x] **Exact promotion mechanism to prod — resolved 2026-10-13** by building
      and proving it for staging first: SSH-triggered `git pull` +
      `docker compose build` + `up -d`, via a GitHub Actions runner joined
      to the tailnet (ephemeral, OAuth-scoped) and a deploy key restricted
      server-side to one script. Promoting to prod reuses this exact
      mechanism, targeting `dnd` instead of `dnd-staging`, plus a
      human-approval gate (see step 5 below).
      
      **Non-obvious gotcha worth remembering:** minting a Tailscale auth
      key via an OAuth client needs the `Auth Keys: Write` scope —
      `Devices: Core Write` alone (which looks like the obvious/sufficient
      scope) 404s silently. Caught via `tailscale/github-action`'s own
      retry loop swallowing the real failure (a bug in `v3`'s bash script —
      no `exit 1` when retries exhaust, so the step reported success
      regardless) — `v4` surfaces it properly.
- [ ] Whether to also close the R2 off-site backup gap for `dnd` while touching
      this area of the stack, since it's related infrastructure work.

## Rough build order, whenever this gets picked back up

1. ~~Check Pi headroom; decide the staging option.~~ **Done** — Option A.
2. ~~Write the initial test suite.~~ **Done** — see above.
3. ~~Stand up the staging environment.~~ **Done (2026-10-09).** `dnd-staging`
   service live on the Pi, own volume, own secret key, seeded with fake
   data via `DEMO=1`, routed at `dnd-staging.gen-kuro.com`.
4. ~~Build the auto-deploy-to-staging GitHub Actions workflow.~~
   **Done (2026-10-13).** See above.
5. ~~Build the manual promote-to-prod workflow.~~ **Done (2026-10-19).** See
   above.
6. Do one full real cycle end to end with an actual small feature, to prove
   the pipeline before trusting it for real work. **Not done yet.**
