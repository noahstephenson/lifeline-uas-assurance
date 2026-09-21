# Discrepancy log

Scenario expectations remain controlled inputs. No expected result was changed to clear a failure.

## D-01 — Demo port collision and ambiguous readiness

- **Observed:** The first loopback smoke test could not bind port 8000 because an unrelated local Python service already owned it.
- **Risk:** The launcher could either fail or mistake an unrelated HTTP response for Lifeline readiness.
- **Decision:** Reserve ports 8765 and 8766 for the Lifeline demo, fail preflight when either is occupied, and require the health response to name the selected run.
- **Verification:** The replay stack returned the expected T-05 run, ten metadata items, 51 history points, and HTTP 200 from Open MCT on the dedicated ports.
- **Scenario impact:** None; assurance policy and expected outcomes did not change.

## D-02 — PX4 launcher was not connected to scenario execution

- **Observed:** The initial `Live` script executed a fake scenario before launching PX4/Gazebo.
- **Risk:** Evidence could be mislabeled or the visual simulator could appear connected when it was not the telemetry source.
- **Decision:** Add a distinct MAVSDK-backed runner, keep PX4/MAVSDK/API inside Ubuntu 24.04, hold at `READY` until Open MCT connects, release through a one-time localhost token, record `source` in every evidence environment, and require two independent SITL action guards.
- **Verification:** Network-free component tests cover PX4 normalization, command acknowledgements, invalid-navigation landing, mission hold, reconnect ordering, error evidence, and the fail-closed action flag.
- **Open item:** A real Ubuntu 24.04/PX4/Gazebo run remains deferred until that environment and MAVSDK are installed. No PX4 completion claim is permitted yet.

## D-03 — Legacy evidence lacked artifact integrity hashes

- **Observed:** The original committed T-05 fixture declared required filenames but not their content hashes.
- **Risk:** A present but modified artifact could still appear complete.
- **Decision:** Record SHA-256 for every required export except the self-referential manifest; treat missing, mismatched, or unchecked artifacts as `INCOMPLETE`.
- **Verification:** Negative tests modify `events.jsonl` and require both the CLI and API to report incomplete evidence. The T-05 reference fixture was regenerated and passes the integrity audit.
- **Scenario impact:** None; the controlled expectations and assurance policy did not change.

## D-04 — The initially reserved demo ports were occupied

- **Observed:** During the 2026-09-20 browser smoke test, unrelated local services legitimately owned ports 8765 and 8766.
- **Risk:** A fixed-port launcher prevents the demo even though safe loopback alternatives exist.
- **Decision:** Keep strict preflight refusal, add explicit `-ApiPort` and `-WebPort` parameters, pass the selected API origin into Vite, and constrain API CORS to localhost origins.
- **Verification:** The replay smoke test on 8875/8876 returned health `ok`, selected `REFERENCE-T05`, evidence `PASS` and complete, dashboard HTTP 200, and a Vite module containing the selected 8875 API origin.
- **Scenario impact:** None; transport configuration does not change assurance behavior.

## D-05 — T-01 execution window was shorter than the stock SITL route allowance

- **Observed:** The 65-second T-01 envelope matched the deterministic source but left insufficient integration allowance for PX4 readiness, mission upload, and stock X500 execution.
- **Risk:** A conforming route could be classified as timed out for integration latency rather than assurance behavior.
- **Decision:** Extend only T-01's execution envelope from 65 to 120 seconds. Its expected states, actions, terminal result, requirements, and hazards are unchanged.
- **Verification:** `CAMPAIGN-20260920-C` reran all twelve scenarios after the change; 12/12 passed and every referenced artifact passed integrity checking.
- **Scenario impact:** Timing allowance only; no expected result was relabeled.

## D-06 — Open MCT 4.1 requires an explicit time-conductor menu

- **Observed:** The first Playwright run stopped before application start because Open MCT 4.1 rejects an empty Conductor configuration.
- **Risk:** Unit-tested view code could appear healthy while the production application never mounted.
- **Decision:** Configure a fixed, recorded-mission UTC window and retain the production browser startup in the qualification suite.
- **Verification:** The focused production-browser case passed after the correction; the full qualification report records all viewport and behavior assertions.
- **Scenario impact:** None; display initialization does not change assurance outputs.

## D-07 — WSL setup path quoting was not parser-qualified

- **Observed:** The first Ubuntu 24.04 setup invocation stopped before system changes because PowerShell rejected the Bash single-quote escape used for the mounted project path.
- **Risk:** A documented one-command environment setup could fail before reaching its deliberate account-creation checkpoint.
- **Decision:** Correct the PowerShell-native escaping, add a repository-wide PowerShell parser gate, and require that gate in CI. The PX4 qualifier now also checks the setup marker, pinned commit, and Node 20 before starting processes, and preserves combined process logs on failed runs when an evidence manifest exists.
- **Verification:** Both setup and qualification launchers pass the parser gate; Ubuntu 24.04 then installed side-by-side and reached its expected first-launch account prompt.
- **Scenario impact:** None; launcher parsing and prerequisite checks do not change assurance policy or expected scenario outcomes.

## D-08 — Ubuntu release detection crossed two shell parsers

- **Observed:** After the non-root Ubuntu account was created, setup incorrectly read the release as a backslash because a Bash variable reference passed through PowerShell quoting.
- **Risk:** A correct Ubuntu 24.04 installation could be rejected before the PX4 download, while a parser-only test would not exercise the cross-shell value.
- **Decision:** Read `/etc/os-release` directly through WSL and parse the `VERSION_ID` record in PowerShell, avoiding cross-shell variable expansion.
- **Verification:** The corrected preflight reports Ubuntu 24.04 from the installed Ubuntu 24.04.5 LTS distribution before setup proceeds.
- **Scenario impact:** None; environment detection does not change assurance behavior or scenario expectations.

## D-09 — Finalization assumed a venv package and delegated path conversion

- **Observed:** The first finalize run found Python 3.12 but no `ensurepip` because `python3-venv` was absent; the direct `wslpath` call also stripped Windows path separators before conversion.
- **Risk:** The pinned simulator could be installed while the Lifeline/MAVSDK environment remained unusable or referenced the wrong checkout path.
- **Decision:** Install Ubuntu's `python3-venv` explicitly, recreate the dedicated venv with `--clear`, and convert drive-qualified Windows paths deterministically to `/mnt/<drive>/...` in PowerShell before Bash quoting.
- **Verification:** Finalization must install the PX4 extra from the mounted repository and pass both `lifeline validate` and `lifeline doctor` inside Ubuntu before qualification begins.
- **Scenario impact:** None; environment bootstrapping does not change requirements, hazards, or expected assurance outcomes.
