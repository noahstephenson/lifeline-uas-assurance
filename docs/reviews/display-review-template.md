# Project Lifeline display review

This form records human inspection; automated tests do not complete it.

- Reviewer:
- Review date:
- Commit:
- Run IDs inspected:
- Browser and viewport:

## Required observations

| Requirement | Inspection question | Pass / fail | Notes or discrepancy |
|---|---|---|---|
| OD-01 | Are mission, assurance, link, navigation, energy, and evidence visible together? |  |  |
| OD-02 | Can every state be distinguished by text or icon without color? |  |  |
| OD-03 | Are transition time, rationale, requirements, hazards, and rejected actions understandable? |  |  |
| OD-04 | Do stale, disconnected, and unavailable data replace any apparently healthy presentation? |  |  |
| OD-05 | Does T-12 replay follow the recorded mission timeline? |  |  |

## Review protocol

1. Inspect nominal T-01 and compound-fault T-05.
2. Inspect stale-data T-11.
3. Stop the evidence service while the console is open and record the displayed state.
4. Replay T-12 and compare the final state with its evidence manifest.
5. Record every failure in `docs/discrepancies.md` before changing the implementation.

Reviewer attestation:

> I inspected the listed synthetic runs. This review addresses display behavior only and
> does not constitute flight, safety, medical, military, or certification validation.
