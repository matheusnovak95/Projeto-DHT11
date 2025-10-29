from blynk import Blynk
import dht
import time
from machine import Pin

sensor = dht.DHT22(Pin(2))
led = Pin(4, Pin.OUT)

led_manual = False

def mensagem_recebida(topic,value):
    global led_manual
    if topic == "ds/Led":
        if value == "1":
            led.on()
        else:
            led.off()


client = Blynk(
    "cHRltLrvuqAbN7uw5yfEYBlgCoXl1MIL",
    wifi_ssid="Wokwi-GUEST",
    wifi_password="",
    callback_func= mensagem_recebida,
    verbose=True
)


while True:
        sensor.measure()
        temp = sensor.temperature()
        umid = sensor.humidity()
        client.publish("ds/Temperatura", str(temp))
        client.publish("ds/Humidade", str(umid))
        if temp > 30:
            led.on()
            client.publish("ds/Led", "1")   #atualiza no Blynk
        else:
            if led_manual:
                led.on()
                client.publish("ds/Led", "1")   # mantém ligado também no app
            else:
                led.off()
                client.publish("ds/Led", "0")

        time.sleep(2)