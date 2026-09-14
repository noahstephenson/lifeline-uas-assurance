---
name: lifeline-cli
description: Operate and inspect the Project Lifeline simulation, replay, validation, evidence, and localhost-only PX4 SITL commands from this repository.
---

# Project Lifeline CLI

Use the installed `lifeline` command from the repository virtual environment. Run `lifeline --json doctor` and `lifeline validate` before controlled work.

Default to `lifeline run --scenario <T-01..T-12> --source fake`. Use `--source px4` only when the user explicitly requests local SITL execution and both action guards are enabled. Never substitute a real endpoint, real coordinates, hardware, operational data, or external command path.

Treat scenario expectations as controlled inputs. If a scenario fails, preserve its result and create a discrepancy instead of changing the expectation to pass.

Use `lifeline evidence --run <run-id>` before describing a run as complete. A missing required export or failed assertion prevents PASS. Use `lifeline figure --run <run-id>` for the generated assurance timeline and `lifeline replay --run <run-id>` for read-only history.

Prefer global `--json` for automation. It must appear before the subcommand, and its single stdout object is the machine-readable contract.
