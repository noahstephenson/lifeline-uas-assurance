# Demonstration walkthrough

The strongest demonstration uses two qualified PX4 replays. T-01 shows the complete delivery workflow. T-05 shows how the assurance logic responds when navigation becomes invalid before handoff.

![Recorded T-01 PX4 SITL replay](../evidence/demo-screenshots/lifeline-t01-demo.gif)

The animation uses the retained T-01 handoff and recovery captures. It is a recorded PX4/Gazebo SITL replay, not live flight footage. Run the command below to inspect the full timeline and use the replay controls.

## Nominal delivery

Start the qualified T-01 replay:

    .\scripts\mission.ps1 -Scenario T-01 -Mode Replay -RunId LFL-T01-PX4-20260922T120613Z-A800

1. Enable Presentation mode.
2. Point out the separate Aircraft, Delivery, and Timeliness cards.
3. Follow the X500 from Logistics Point Alpha to Echo Aid Station.
4. On the timeline, find `DELIVERY_ZONE_ARRIVAL`, `LANDING_OBSERVED`, and `DISARM_OBSERVED`. These events come from simulator telemetry.
5. Find `UNLOADING_STARTED`, `UNLOADING_COMPLETE`, and the accepted receipt. These events come from the receiving-station model.
6. Seek to a moment before the receipt and open "Explain this moment." The later receipt and final recovery should not appear.
7. Resume the replay and show the accepted handoff, second departure, return flight, and observed recovery.

The final outcomes are `RECOVERED`, `ACCEPTED`, and `ON_TIME`.

## Compound fault

Start the corrected T-05 replay:

    .\scripts\mission.ps1 -Scenario T-05 -Mode Replay -RunId LFL-T05-PX4-20260922T185205Z-CDF9

1. Seek to about 22.1 seconds.
2. Show the link-loss `WATCH` transition followed by invalid navigation.
3. Open "Explain this moment." The selected action is Controlled landing, and `RETURN` appears as a rejected alternative.
4. Continue to the observed landing. The Aircraft card reads Landed and stopped.
5. Check the logistics result. Delivery remains `NOT_COMPLETED`, and package custody remains `AIRCRAFT`.

The degraded link and navigation values are scripted Lifeline inputs. MAVSDK continues to report telemetry from the unchanged PX4 estimator.

## Receiver cases

The synthetic scenarios make the logistics boundary easy to inspect:

- T-13 ends `UNCONFIRMED` because no receipt arrives.
- T-14 ends `REJECTED` because the receipt names the wrong package. It does not satisfy the original request.
- T-15 records both `ACCEPTED` and `LATE`.

## Reproduce the qualification

PX4 qualification requires Ubuntu 24.04 under WSL2, PX4 v1.17.0 at commit `d6f12ad1c4`, Gazebo Harmonic, MAVSDK 3.17.2, and explicit loopback SITL authorization.

    .\scripts\qualify-px4.ps1 -Scenario Smoke
    .\scripts\qualify-px4.ps1 -Scenario T-01
    .\scripts\qualify-px4.ps1 -Scenario T-05
    .\.venv\Scripts\lifeline.exe campaign run --id CAMPAIGN-LOCAL-V11
    .\.venv\Scripts\lifeline.exe campaign audit --id CAMPAIGN-LOCAL-V11

## Screenshot set

- [T-01 handoff](../evidence/demo-screenshots/px4-t01-handoff.png)
- [T-01 recovery](../evidence/demo-screenshots/px4-t01-recovered.png)
- [T-05 decision](../evidence/demo-screenshots/px4-t05-decision.png)
- [T-05 landing](../evidence/demo-screenshots/px4-t05-landed.png)

The demonstration covers a fictional simulation. It is not evidence of clinical suitability, real-flight performance, operational safety, certification, or human usability.
