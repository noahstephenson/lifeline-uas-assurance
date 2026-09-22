# Medical Resupply Mission Lab demonstration

## Short demonstration script

1. Start the nominal qualified replay:

       .\scripts\mission.ps1 -Scenario T-01 -Mode Replay -RunId LFL-T01-PX4-20260922T120613Z-A800

2. Enable Presentation mode. In the outcome strip, explain that Aircraft, Delivery, and Timeliness are independent. Follow the outbound X500 path to Echo Aid Station.
3. On the timeline, identify telemetry-sourced DELIVERY_ZONE_ARRIVAL, LANDING_OBSERVED, and DISARM_OBSERVED. Then identify modeled-station UNLOADING_STARTED, UNLOADING_COMPLETE, and the matched ACCEPTED receipt. A command acknowledgement is not used as observed completion.
4. Seek to a point before the receipt and select Explain this moment. Confirm the later receipt and final recovery do not appear. Resume and show the accepted, on-time handoff, re-departure, return, and observed recovery.
5. Start the compound-fault replay:

       .\scripts\mission.ps1 -Scenario T-05 -Mode Replay -RunId LFL-T05-PX4-20260922T185205Z-CDF9

6. Seek to about 22.1 seconds. Show the link-loss WATCH transition followed by invalid navigation. The dashboard presents Controlled landing in plain language, records RETURN as rejected, and later shows Landed and stopped. Delivery remains NOT_COMPLETED and package custody remains AIRCRAFT. Explain that the degraded link/navigation values were scripted Lifeline inputs while MAVSDK continued to report the PX4 vehicle connected in MISSION mode.
7. Briefly show the synthetic receiver outcomes: T-13 UNCONFIRMED/ABSENT, T-14 REJECTED with AIRCRAFT custody, and T-15 ACCEPTED plus LATE.

## Reproduce qualification locally

Ubuntu 24.04 WSL2, PX4 v1.17.0 at d6f12ad1c4, Gazebo Harmonic, MAVSDK 3.17.2, and explicit loopback SITL authorization are required.

    .\scripts\qualify-px4.ps1 -Scenario Smoke
    .\scripts\qualify-px4.ps1 -Scenario T-01
    .\scripts\qualify-px4.ps1 -Scenario T-05
    .\.venv\Scripts\lifeline.exe campaign run --id CAMPAIGN-LOCAL-V11
    .\.venv\Scripts\lifeline.exe campaign audit --id CAMPAIGN-LOCAL-V11

## Best dashboard captures

- Nominal handoff: ../evidence/demo-screenshots/px4-t01-handoff.png
- Nominal recovery: ../evidence/demo-screenshots/px4-t01-recovered.png
- Compound-fault decision: ../evidence/demo-screenshots/px4-t05-decision.png
- Compound-fault landing: ../evidence/demo-screenshots/px4-t05-landed.png

## Claims and limits

The deterministic model distinguishes flight completion from logistics completion, accepts a receipt only when mission/request/package/recipient identifiers match, and produces traceable replay evidence. Results are limited to the documented fictional simulation. They do not establish clinical suitability, real-flight performance, operational safety, certification, or human usability.
