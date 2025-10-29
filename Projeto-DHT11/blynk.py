from umqttsimple import *
import _thread
import random


class Blynk:
    def __init__(self,
                 blynk_auth_token,
                 callback_func=None,
                 wifi_ssid=None,
                 wifi_password="",
                 verbose=False,
                 ):
        self.callback = callback_func
        self.verbose = verbose
        self.wifi_ssid = wifi_ssid
        self.wifi_password = wifi_password
        self.abort = False

        self.mqtt_server = "ny3.blynk.cloud"
        self.mqtt_port = 1883
        self.mqtt_user = "device"
        self.mqtt_client_id = Blynk.__get_random_device_id(20)
        self.mqtt_password = blynk_auth_token
        if self.verbose:
            print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
            print("Client ID:", self.mqtt_client_id)
        # Conecta ao Wi-Fi apenas em MicroPython
        if is_micropython:
            if self.verbose:
                print(f"Conectando ao Wi‑Fi {self.wifi_ssid}")
            self.station = self.__wifi_connect()
            if not self.station.isconnected():
                print(f"Falha ao conectar na rede {self.wifi_ssid}!")
                sys.exit(1)
            if self.verbose:
                print(f"Conectado ao WiFi {self.wifi_ssid}")
        else:
            if self.verbose:
                print("Executando em CPython – conexão Wi‑Fi ignorada")
        # Conecta ao MQTT Broker
        if self.verbose:
            print(f"Conectando ao MQTT Broker {self.mqtt_server}")
        self.mqtt_client = MQTTClient(self.mqtt_client_id,
                                      self.mqtt_server,
                                      self.mqtt_port,
                                      self.mqtt_user,
                                      self.mqtt_password)
        self.mqtt_client.connect()
        if self.verbose:
            print("MQTT Broker conectado")
        if self.callback is not None:
            self.mqtt_client.set_callback(self.message_received)
            _thread.start_new_thread(self.check_message_loop, ())

    def check_message_loop(self):
        while True:
            self.mqtt_client.check_msg()
            if self.abort:
                break
            time.sleep(0.5)

    def message_received(self, topic, msg):
        topic_list = topic.decode().split('/')
        self.callback('/'.join(topic_list[1:]), msg.decode())

    def __get_random_device_id(n):
        caracteres = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        return ''.join(random.choice(caracteres) for _ in range(n))

    def __wifi_connect(self):
        import network
        station = network.WLAN(network.STA_IF)
        station.active(True)
        station.disconnect()
        station.connect(self.wifi_ssid, self.wifi_password)
        for _ in range(150):
            if station.isconnected():
                break
            time.sleep(0.1)
        return station

    def subscribe(self, topic):
        if self.verbose:
            print(f"Subscribing '{topic}'")
        if self.callback is None:
            print("ERRO: Subscribe não permitido. Callback não informado!")
            sys.exit(1)
        self.mqtt_client.subscribe(f"{topic}")

    def publish(self, topic, value):
        if self.verbose:
            print(f"Publicando '{value}' no tópico '{topic}'")
        self.mqtt_client.publish(f"{topic}", value)

    def disconnect(self):
        self.abort = True
        time.sleep(1)
        self.mqtt_client.disconnect()
        self.station.disconnect()

# ++++++++++++++++++++++ EXEMPLO DE USO ++++++++++++++++++++++++++++++
if __name__ == "__main__":

    def subscribe_message(topic, value):
        print(f"Recebi {value} do topico {topic}")
        if topic == "ds/Luz":
            if value == '0':
                print("Luz desligada")
            else:
                print("Luz ligada")
        if topic == "ds/Servo":
            angulo = int(value)
            print(f"Servo com angulo {angulo}")

    client = Blynk("6_KTPslU2e2uI2rk-Dt5v7VSXfuAz7Kf",
                   wifi_ssid="Wokwi-GUEST",
                   callback_func=subscribe_message,
                   verbose=True)

    client.subscribe(f"downlink/#")

    for i in range(10):
        client.publish("ds/Umidade", f"{i}")
        time.sleep(1)

