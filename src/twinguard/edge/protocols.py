"""Real QoS1 MQTT and read-only OPC UA adapters."""

import asyncio
import os
import time
import uuid
from pathlib import Path
import paho.mqtt.client as mqtt
from .contracts import now, Envelope
from .storage import engine, get, audit, put
from .ingestion import ingest, topic
from .artifacts import ArtifactStore


def mqtt_client(identity, password, client_id, on_message=None):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=False)
    client.username_pw_set(identity, password)
    client.max_queued_messages_set(10000)
    client.reconnect_delay_set(1, 10)
    if os.environ.get("TWINGUARD_MQTT_CA"):
        client.tls_set(ca_certs=os.environ["TWINGUARD_MQTT_CA"])
    if on_message:
        client.on_message = on_message
    return client


def subscribe():
    db = engine()
    store = ArtifactStore(os.environ["TWINGUARD_ARTIFACTS"])

    def on_message(client, userdata, msg):
        # The broker ACL binds source username to exact source topics. Payload identity is never used to establish identity.
        pieces = msg.topic.split("/")
        source = pieces[4] if len(pieces) == 6 else ""
        with db.connect() as c:
            reg = get(c, "source", source)
        identity = reg["transport_identity"] if reg else "unknown"
        ingest(db, msg.payload, identity, msg.topic, store)
        client.ack(msg.mid, msg.qos)  # Accepted OR durably quarantined effects are committed.

    client = mqtt_client(
        "ingestion", os.environ["TWINGUARD_INGEST_PASSWORD"], "edge-ingestion", on_message
    )
    client.manual_ack_set(True)

    def connected(c, u, f, rc, p):
        c.subscribe("twinguard/v1/plant-01/+/+/+", qos=1)

    client.on_connect = connected
    client.connect(
        os.environ.get("TWINGUARD_MQTT_HOST", "localhost"),
        int(os.environ.get("TWINGUARD_MQTT_PORT", "1883")),
    )
    client.loop_forever(retry_first_connection=True)


def publish(envelopes, password, host=None, port=None, delay=0):
    envelopes = list(envelopes)
    if not envelopes:
        return []
    source = envelopes[0].source_id
    client = mqtt_client(source, password, "publisher-" + source)
    client.connect(
        host or os.environ.get("TWINGUARD_MQTT_HOST", "localhost"),
        int(port or os.environ.get("TWINGUARD_MQTT_PORT", "1883")),
    )
    client.loop_start()
    sent = []
    try:
        for env in envelopes:
            info = client.publish(
                topic(source, env.site_id, env.kind), env.model_dump_json(), qos=1
            )
            info.wait_for_publish(timeout=20)
            if not info.is_published():
                raise RuntimeError("MQTT delivery not acknowledged")
            sent.append(
                {
                    "message_id": env.message_id,
                    "observation_id": env.observation.observation_id if env.observation else None,
                    "emitted_at": env.emitted_at.isoformat(),
                    "puback_at": now().isoformat(),
                }
            )
            if delay:
                time.sleep(delay)
    finally:
        client.disconnect()
        client.loop_stop()
    return sent


async def opc_server(bundle, endpoint):
    from asyncua import Server, ua
    from twinguard.core.observations import load_public_observations
    from twinguard.core.contracts import SensorObservation

    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    idx = await server.register_namespace("urn:twinguard:measured")
    obj = await server.nodes.objects.add_object(idx, "MeasuredChannels")
    nodes = {}
    record_nodes = {}
    samples = [
        r for r in load_public_observations(Path(bundle)) if isinstance(r, SensorObservation)
    ]
    for sensor in sorted({r.sensor_id for r in samples}):
        record = next(r for r in samples if r.sensor_id == sensor)
        node = await obj.add_variable(ua.NodeId(sensor, idx), sensor, float(record.value))
        await node.add_property(ua.NodeId(sensor + ".Unit", idx), "EngineeringUnits", record.unit)
        record_nodes[sensor] = await obj.add_variable(
            ua.NodeId(sensor + ".Record", idx), sensor + "Record", record.model_dump_json()
        )
        nodes[sensor] = node
    async with server:
        while True:
            for record in samples:
                value = ua.DataValue(ua.Variant(float(record.value), ua.VariantType.Double))
                value.SourceTimestamp = record.acquired_at
                await nodes[record.sensor_id].write_value(value)
                await record_nodes[record.sensor_id].write_value(record.model_dump_json())
                await asyncio.sleep(0.03)
            await asyncio.sleep(1)


async def opc_client(endpoint, once=False):
    from asyncua import Client
    from twinguard.core.contracts import SensorObservation

    db = engine()
    while True:
        try:
            client = Client(endpoint)
            security = os.environ.get("TWINGUARD_OPCUA_SECURITY")
            if security:
                if len(security.split(",")) < 5 or not Path(security.split(",")[4]).is_file():
                    raise ValueError("Pinned approved OPC UA server certificate required")
                await client.set_security_string(security)
            elif os.environ.get("TWINGUARD_OPCUA_LAB", "0") != "1":
                raise ValueError("Explicit loopback laboratory profile or secure channel required")
            async with client:
                idx = await client.get_namespace_index("urn:twinguard:measured")
                from asyncua import ua

                with db.connect() as c:
                    reg = get(c, "source", "opcua-demo")
                if reg is None:
                    raise ValueError("OPC UA source not registered")
                while True:
                    for sensor in reg["sensors"]:
                        node = client.get_node(ua.NodeId(sensor, idx))
                        dv = await node.read_data_value()
                        raw = dv.Value.Value
                        if not isinstance(raw, (float, int)):
                            raise ValueError("Unexpected OPC UA datatype")
                        unit = await client.get_node(ua.NodeId(sensor + ".Unit", idx)).read_value()
                        if unit != reg["sensors"][sensor]["unit"]:
                            raise ValueError("OPC UA engineering unit mismatch")
                        public_record = await client.get_node(
                            ua.NodeId(sensor + ".Record", idx)
                        ).read_value()
                        observation = SensorObservation.model_validate_json(public_record)
                        if observation.value != raw:
                            continue  # Non-atomic companion update; retry on the next read, never combine mismatched records.
                        with db.begin() as c:
                            put(
                                c,
                                "opcua_status",
                                sensor,
                                {
                                    "source_timestamp": str(dv.SourceTimestamp),
                                    "server_timestamp": str(dv.ServerTimestamp),
                                    "status": str(dv.StatusCode),
                                    "node_id": node.nodeid.to_string(),
                                    "at": now().isoformat(),
                                },
                            )
                        if not dv.StatusCode.is_good():
                            observation = observation.model_copy(update={"quality": "invalid"})
                        env = Envelope(
                            message_id="opc-" + str(uuid.uuid4()),
                            source_id="opcua-demo",
                            sequence=observation.sequence_number or 0,
                            emitted_at=now(),
                            mode="simulation_replay",
                            replay_acquired_at=now(),
                            observation=observation,
                            provenance_id=observation.provenance_id,
                        )
                        ingest(
                            db, env.model_dump_json().encode(), "opcua-adapter", topic("opcua-demo")
                        )
                    if once:
                        return
                    await asyncio.sleep(1)
        except Exception as exc:
            with db.begin() as c:
                audit(c, "opcua_disconnected", error=str(exc)[:500])
            if once:
                raise
            await asyncio.sleep(2)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("role", choices=["mqtt", "opcua-server", "opcua-client"])
    p.add_argument("--bundle", default="/measurements")
    p.add_argument("--endpoint", default="opc.tcp://127.0.0.1:4840/twinguard/")
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    if args.role == "mqtt":
        subscribe()
    elif args.role == "opcua-server":
        asyncio.run(opc_server(args.bundle, args.endpoint))
    else:
        asyncio.run(opc_client(args.endpoint, args.once))
