# Architecture

```mermaid
flowchart LR
  PX4[PX4 SITL + Gazebo X500] -->|MAVLink| ADAPTER[MAVSDK adapter]
  SCENARIO[Scenario controller] --> NORMALIZER[Snapshot normalizer]
  ADAPTER --> NORMALIZER
  NORMALIZER --> ENGINE[Pure assurance engine]
  ENGINE -->|opt-in local SITL action| ADAPTER
  NORMALIZER --> EVIDENCE[Evidence service]
  ENGINE --> EVIDENCE
  EVIDENCE -->|REST + WebSocket| MCT[Open MCT Lifeline plugin]
  EVIDENCE --> EXPORT[Verification export + timeline]
```

The normalizer is the only boundary allowed to combine vehicle telemetry and synthetic
conditions. The assurance package depends only on domain models and configuration.
Evidence is append-only during a run. Live and replay sources publish the same canonical
message envelope.

