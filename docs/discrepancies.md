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
- **Decision:** Add a distinct MAVSDK-backed runner, record `source` in every evidence environment, route `--source px4` through it, and require two independent SITL action guards.
- **Verification:** Network-free component tests cover PX4 normalization and invalid-navigation landing; the CLI fails closed with the controlled action flag disabled.
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
