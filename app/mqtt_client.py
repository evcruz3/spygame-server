import json
import paho.mqtt.client as mqtt
import asyncio
import paho.mqtt.publish as publish
from fastapi.encoders import jsonable_encoder
from datetime import datetime


class MQTTClient:
    def __init__(self, host="localhost", port=1883):
        self.client = mqtt.Client(clean_session=True)
        # self.client.will_set("/events/+/tasks", "Offline", qos=2, retain=True)
        # self.client.will_set("/events/+/tasks/+/participants", "Offline", qos=2, retain=True)
        # self.client.will_set("/events/+/tasks/+/state", "Offline", qos=2, retain=True)
        # self.client.will_set("/events/+/players/+/life", "Offline", qos=2, retain=True)
        # self.client.will_set("/events/+/players/+/task", "Offline", qos=2, retain=True)
        # self.client.will_set("/events/+/players/+/role", "Offline", qos=2, retain=True)
        self.client.on_message = self._on_message
        self.host = host
        self.port = port
        # self.topics = ["events/+", "events/+/tasks/+"]
        self.topics = ["/events/+/tasks"]
        self.qos = 2
        self.client.connect(self.host, self.port)

    def _on_message(self, client, userdata, message):
        print(f"Received message on topic {message.topic}: {message.payload}")

    def subscribe(self, topic):
        self.topics.append(topic)
        self.client.subscribe(topic, qos=self.qos)

    def publish(self, topic, message : dict):
        # if self.client.is_connected() == False:
        #     print("mqtt client got disconnected. reconnecting...")
        #     self.client.connect(self.host, self.port)
        #     print("mqtt client reconnected")
        # result = self.client.publish(topic, message, self.qos, retain=True)
        # result.wait_for_publish(1.2)
        # if result.rc == mqtt.MQTT_ERR_SUCCESS:
        #     print("Message delivered successfully!")
        #     print(f"topic: {topic}")
        #     print(f"message: {message}")
        # else:
        #     print("Failed to deliver message. Error code: {}".format(result.rc))
        message['timestamp'] = datetime.utcnow()
        payload = json.dumps(jsonable_encoder(message))
        publish.single(topic, payload, self.qos, True, self.host, self.port)


    def start(self):
        print("Starting mqqt client")
        self.client.loop_forever()
        print("mqtt client finished")


    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()


