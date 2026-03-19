import json
import time
import paho.mqtt.client as mqtt

BROKER_HOST = "150.214.112.231"
BROKER_PORT = 1883
TOPIC = "hackathon/olivia"

QOS = 0
RETAIN = False


def publish_alert(payload: dict):
    client = mqtt.Client()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("MQTT conectado")
        else:
            print(f"Error MQTT: {rc}")

    client.on_connect = on_connect

    client.connect(BROKER_HOST, BROKER_PORT, 60)
    client.loop_start()

    payload["timestamp"] = int(time.time())

    payload_str = json.dumps(payload, ensure_ascii=False)

    result = client.publish(TOPIC, payload_str, qos=QOS, retain=RETAIN)
    result.wait_for_publish()

    client.loop_stop()
    client.disconnect()

    print(f"Alerta enviada: {payload['parcel_id']}")