# Medical logistics basis

Project Lifeline models a fictional replenishment request for sealed, non-temperature-
controlled medical consumables. It is a logistics and mission-assurance example, not a
clinical kit specification.

## Source-supported facts

- The FAA documents certificated UAS package-delivery operations that have transported
  medical supplies between health facilities:
  https://www.faa.gov/uas/advanced_operations/package_delivery_drone
- WHO describes standardized, pre-packed emergency health kits as a way to mobilize
  medicines and supplies quickly:
  https://www.who.int/emergencies/emergency-health-kits
- WHO primary-health-care supply guidance lists individually protected gauze bandages,
  while WHO emergency kit material includes sterile gauze, adhesive tape, and examination
  gloves:
  https://cdn.who.int/media/docs/default-source/ntds/neglected-tropical-diseases-non-disease-specific/medical-supplies-and-equipment-for-primary-health-care--echo.pdf
- FDA guidance explains that medical-glove packaging identifies material and that damaged
  gloves should not be used:
  https://www.fda.gov/medical-devices/personal-protective-equipment-infection-control/medical-gloves

## Fictional engineering assumptions

- The request, sites, identifiers, quantities, 1.8 kg package mass, delivery deadline,
  route, unloading duration, and receiving-station behavior are fictional.
- Package mass does not alter the stock PX4 X500 dynamics. It is recorded as a mission
  planning input only.
- The package is assumed sealed and dry. No temperature range or cold-chain behavior is
  modeled.
- The deadline is a logistics service target, not a patient-survival or clinical threshold.
- The receiving station and unloading process are deterministic software models.

## Simulator measurements and modeled values

PX4 sources vehicle position, altitude, battery percentage, flight mode, mission progress,
and connection state during SITL runs. Link-policy inputs, navigation confidence,
energy-feasibility quantities, package custody, unloading, recipient readiness, and receipt
messages are modeled by Lifeline and are labeled as such.

