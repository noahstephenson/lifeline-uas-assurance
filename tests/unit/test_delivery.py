from lifeline.delivery import DeliveryThread, load_mission_contract
from lifeline.models import DeliveryOutcome, PackageCustodyState, ReceiptStatus, TimelinessOutcome


def test_nominal_landed_handoff_requires_dwell_and_matching_receipt():
    thread = DeliveryThread(load_mission_contract())
    thread.update(
        sim_time_s=2,
        dispatched=True,
        at_delivery_zone=False,
        landed=False,
        disarmed=False,
        terminal=False,
    )
    arrived = thread.update(
        sim_time_s=40,
        dispatched=True,
        at_delivery_zone=True,
        landed=False,
        disarmed=False,
        terminal=False,
    )
    assert arrived.outcome == DeliveryOutcome.PENDING
    handoff_ready = thread.update(
        sim_time_s=42,
        dispatched=True,
        at_delivery_zone=True,
        landed=True,
        disarmed=True,
        terminal=False,
    )
    assert handoff_ready.handoff_progress == 0
    still_unloading = thread.update(
        sim_time_s=46,
        dispatched=True,
        at_delivery_zone=True,
        landed=True,
        disarmed=True,
        terminal=False,
    )
    assert still_unloading.outcome == DeliveryOutcome.PENDING
    accepted = thread.update(
        sim_time_s=47,
        dispatched=True,
        at_delivery_zone=True,
        landed=True,
        disarmed=True,
        terminal=False,
    )
    assert accepted.outcome == DeliveryOutcome.ACCEPTED
    assert accepted.custody == PackageCustodyState.RECEIVING_STATION
    assert accepted.receipt_status == ReceiptStatus.ACCEPTED
    assert accepted.timeliness == TimelinessOutcome.ON_TIME


def test_arrival_without_landing_never_becomes_delivery():
    thread = DeliveryThread(load_mission_contract())
    thread.update(
        sim_time_s=40,
        dispatched=True,
        at_delivery_zone=True,
        landed=False,
        disarmed=False,
        terminal=False,
    )
    terminal = thread.update(
        sim_time_s=60,
        dispatched=True,
        at_delivery_zone=False,
        landed=False,
        disarmed=False,
        terminal=True,
    )
    assert terminal.outcome == DeliveryOutcome.NOT_COMPLETED
    assert terminal.receipt_status == ReceiptStatus.PENDING


def test_absent_receipt_keeps_delivery_unconfirmed_despite_station_custody():
    thread = DeliveryThread(load_mission_contract())
    thread.update(
        sim_time_s=40,
        dispatched=True,
        at_delivery_zone=True,
        landed=True,
        disarmed=True,
        terminal=False,
        response_mode="absent",
    )
    status = thread.update(
        sim_time_s=45,
        dispatched=True,
        at_delivery_zone=True,
        landed=True,
        disarmed=True,
        terminal=False,
        response_mode="absent",
    )
    assert status.custody == PackageCustodyState.RECEIVING_STATION
    assert status.receipt_status == ReceiptStatus.ABSENT
    assert status.outcome == DeliveryOutcome.UNCONFIRMED


def test_receipts_are_identifier_checked_and_idempotent():
    thread = DeliveryThread(load_mission_contract())
    contract = thread.contract
    assert not thread.ingest_receipt(
        receipt_id="RCPT-WRONG",
        mission_id=contract.mission_id,
        request_id=contract.request_id,
        package_id="OTHER-PACKAGE",
        recipient_id=contract.recipient.id,
        sim_time_s=45,
    )
    assert not thread.ingest_receipt(
        receipt_id="RCPT-WRONG",
        mission_id=contract.mission_id,
        request_id=contract.request_id,
        package_id=contract.package.id,
        recipient_id=contract.recipient.id,
        sim_time_s=46,
    )
    assert thread.events[-1].event_type == "RECEIPT_DUPLICATE"


def test_wrong_package_rejection_keeps_package_with_aircraft():
    thread = DeliveryThread(load_mission_contract())
    thread.update(
        sim_time_s=40,
        dispatched=True,
        at_delivery_zone=True,
        landed=True,
        disarmed=True,
        terminal=False,
        response_mode="wrong_package",
    )
    status = thread.update(
        sim_time_s=45,
        dispatched=True,
        at_delivery_zone=True,
        landed=True,
        disarmed=True,
        terminal=False,
        response_mode="wrong_package",
    )
    assert status.outcome == DeliveryOutcome.REJECTED
    assert status.receipt_status == ReceiptStatus.REJECTED
    assert status.custody == PackageCustodyState.AIRCRAFT
