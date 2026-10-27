import paho.mqtt.client as mqtt
client = mqtt.Client()
client.publish("topic", "value")
