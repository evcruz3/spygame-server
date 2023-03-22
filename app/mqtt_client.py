import paho.mqtt.client as mqtt
import asyncio

class MQTTClient:
    def __init__(self, host="localhost", port=1883):
        self.client = mqtt.Client()
        self.client.on_message = self._on_message
        self.host = host
        self.port = port
        # self.topics = ["events/+", "events/+/tasks/+"]
        self.topics = []
        self.qos = 1
        self.running = False

    def _on_message(self, client, userdata, message):
        print(f"Received message on topic {message.topic}: {message.payload}")

    def subscribe(self, topic):
        self.topics.append(topic)
        self.client.subscribe(topic, qos=self.qos)

    def publish(self, topic, message):
        print(f"topic: {topic}")
        print(f"message: {message}")
        self.client.publish(topic, message)

    def start(self):
        print("Starting mqqt client")
        self.client.connect(self.host, self.port)
        for topic in self.topics:
            self.client.subscribe(topic, qos=self.qos)
        self.running = True
        # self.client.loop_forever()
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, self.client.loop_forever)
        print("mqtt client started")

    def stop(self):
        self.running = False
        self.client.disconnect()
        self.client.loop_stop()


