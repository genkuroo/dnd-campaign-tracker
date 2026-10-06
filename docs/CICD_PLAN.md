# Plan: a real dev → test → staging → prod pipeline

**Status: planned, not yet built.** This is a design doc to pick back up later,
not a runbook for something that exists yet. Written 2026-09-30, after
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
2. **A staging environment.** Three real options, tradeoffs below — **not
   decided yet, pick this when the work actually starts:**

   | Option | Cost | Notes |
   |---|---|---|
   | A second container on the same Pi (`dnd-staging` service in `homelab-pi`'s compose file, own subdomain, own volume seeded with fake campaign data) | Free | Consistent with the rest of the homelab's self-hosted philosophy. Shares the Pi's limited resources (4GB total, ~7 services already running) and shares its fate — if the Pi goes down, staging does too. **Check actual headroom on the Pi before committing to this** — not verified as of this writing. |
   | A small environment elsewhere (e.g. Fly.io's free tier, now used purely as disposable staging rather than as prod) | Likely free at this scale | Doesn't compete with the Pi's resources. Mirrors a real, common pattern: durable prod on owned hardware, disposable staging in the cloud. |
   | Local-only testing (Docker Compose on a dev machine) before deploying straight to the Pi | Free | Simplest, but not a "real live pre-prod environment" — weaker simulation of the actual workflow this plan exists to practice. |

3. **Two GitHub Actions workflows**, same shape as `url-shortener-k8s`:
   - On every push to `main`: run the test suite, then (if staging is a
     remote environment) deploy to staging automatically.
   - A separate, manual `workflow_dispatch` workflow: promotes the exact
     tested commit to prod. If staging is a container on the Pi itself, this
     step is likely an SSH-triggered `git pull` + `docker compose up -d
     --build` on the Pi, not a GHCR-based image bump like `url-shortener-k8s`
     — worth deciding once the staging option is picked, since it changes
     the mechanics meaningfully (this app isn't containerized through a
     registry today, it builds in place from source on the host).

## Open decisions

- [x] **Which staging option — Option A, a second container on the Pi.**
      Resolved 2026-10-05: checked the Pi directly over SSH. 2.7GB RAM free,
      and while `df` showed only 4.7GB disk free, 2.2GB of that is reclaimable
      Docker build cache, not real usage — the `dnd` volume itself is 700KB
      and the container runs near-0% CPU at idle. Same pattern as the existing
      `stock-demo`/`fitness-demo` sibling services.
- [x] **Scope of the initial test suite — resolved 2026-10-05,** see above.
- [ ] Exact promotion mechanism to prod, now that staging is on-Pi (likely
      SSH-triggered `git pull` + `docker compose up -d --build`, not a
      registry-based image bump — this app isn't containerized through a
      registry today).
- [ ] Whether to also close the R2 off-site backup gap for `dnd` while touching
      this area of the stack, since it's related infrastructure work.

## Rough build order, whenever this gets picked back up

1. ~~Check Pi headroom; decide the staging option.~~ **Done** — Option A.
2. ~~Write the initial test suite.~~ **Done** — see above.
3. Stand up the staging environment (`dnd-staging` service in homelab-pi's
   compose file, own subdomain/volume), seeded with fake data.
4. Build the auto-deploy-to-staging GitHub Actions workflow.
5. Build the manual promote-to-prod workflow.
6. Do one full real cycle end to end with an actual small feature, to prove
   the pipeline before trusting it for real work.
