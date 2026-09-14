# Concept of operations

The operator selects a controlled scenario and starts the local demonstration. PX4 SITL
executes a fictional outbound route, records a notional package acknowledgement, and
returns. The scenario controller may alter abstract link availability, navigation
confidence, energy demand, or telemetry freshness. The assurance engine evaluates those
conditions at 2 Hz. Open MCT displays the aircraft, health, recommendation, rationale, and
verification state. A reviewer later replays the same evidence without PX4.

Open MCT never commands the aircraft. During controlled runs, only the scenario file may
inject conditions. Optional manual injection creates an exploratory run that cannot count
toward verification coverage.

