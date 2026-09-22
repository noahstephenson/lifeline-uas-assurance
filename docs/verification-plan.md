# Verification plan

The project follows an executable V-model: needs map to requirements; requirements map to
architecture and hazards; each test maps back to requirements and controlled evidence.

Levels are schema, unit, component, integration, end-to-end, and repository-content audit. A scenario
passes only if all declared assertions pass and every required evidence file exists.
Coverage metrics include requirement, state, transition, decision-record completeness,
scenario completion, and deterministic replay. These metrics are not safety validation.

The controlled local campaign is executed with `lifeline campaign run`. Its aggregate
report is advisory: the release audit independently rechecks every run's required files
and SHA-256 values. The fake-source threshold, automated browser display qualification,
and PX4 SITL qualification remain separate gates. The display gate checks observable
behavior at two viewports; it is not evidence of a human usability study.

Evidence integrity has three failure classes:

- **missing:** a manifest-declared artifact is absent;
- **mismatched:** an artifact's current SHA-256 differs from the manifest;
- **unchecked:** a legacy manifest does not declare a hash.

Any class forces the effective result to `INCOMPLETE`.
