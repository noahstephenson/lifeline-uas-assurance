# Decision policy v0.1

Priority is: invalid/stale critical input, critical energy, invalid navigation, sustained
operator-link loss, mission degradation, then nominal progression.

- Unknown critical state: `UNKNOWN`; abort in preflight or controlled land while airborne.
- Energy at/below zero margin: `TERMINATE` and controlled land.
- Energy below recovery boundary during outbound: `RECOVER` and return.
- Navigation below 0.40: `TERMINATE`; return is rejected.
- Link loss under 3 seconds: `WATCH`, no irreversible action.
- Sustained link loss with healthy navigation/energy: continue outbound; return after delivery.
- Recovery from `WATCH`/`DEGRADED` requires five healthy seconds.
- `TERMINATE` does not automatically revert.

Thresholds are synthetic educational configuration and do not represent an airworthiness
or operational safety determination.

