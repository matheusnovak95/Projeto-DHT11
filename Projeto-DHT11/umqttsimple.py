import sys
import time
# Detecta se estamos rodando em MicroPython
is_micropython = sys.implementation.name == "micropython"

# ++++++++++++++++++++++ MQTT IMPLEMENTATION ++++++++++++++++++++++++++++++
# Em MicroPython, importa os módulos específicos; no CPython, usa os padrão.
try:
    import usocket as socket
except ImportError:
    import socket

try:
    import ustruct as struct
except ImportError:
    import struct

import ssl

# Funções utilitárias para envio/recebimento
def _send(sock, data, length=None):
    if is_micropython:
        # Em MicroPython, usa write() ignorando o parâmetro length.
        return sock.write(data)
    else:
        if length is None:
            return sock.sendall(data)
        else:
            return sock.sendall(data[:length])

def _recv(sock, n):
    if is_micropython:
        return sock.read(n)
    else:
        return sock.recv(n)

class MQTTException(Exception):
    pass

class MQTTClient:
    def __init__(self, client_id, server, port=0, user=None, password=None, keepalive=0,
                 ssl_enabled=False, ssl_params={}, verbose=False):
        if port == 0:
            port = 8883 if ssl_enabled else 1883
        # Converte para bytes se necessário
        self.client_id = client_id.encode('utf-8') if isinstance(client_id, str) else client_id
        self.sock = None
        self.server = server
        self.port = port
        self.ssl_enabled = ssl_enabled
        self.ssl_params = ssl_params
        self.pid = 0
        self.cb = None
        self.user = user.encode('utf-8') if isinstance(user, str) and user is not None else user
        self.pswd = password.encode('utf-8') if isinstance(password, str) and password is not None else password
        self.keepalive = keepalive
        self.lw_topic = None
        self.lw_msg = None
        self.lw_qos = 0
        self.lw_retain = False
        self.verbose = verbose

    def _send_str(self, s):
        if isinstance(s, str):
            s = s.encode('utf-8')
        _send(self.sock, struct.pack("!H", len(s)))
        _send(self.sock, s)

    def _recv_len(self):
        n = 0
        sh = 0
        while True:
            b = _recv(self.sock, 1)
            if not b:
                raise OSError("Socket closed")
            b = b[0]
            n |= (b & 0x7f) << sh
            if not b & 0x80:
                return n
            sh += 7

    def set_callback(self, f):
        self.cb = f

    def set_last_will(self, topic, msg, retain=False, qos=0):
        assert 0 <= qos <= 2
        assert topic
        self.lw_topic = topic.encode('utf-8') if isinstance(topic, str) else topic
        self.lw_msg = msg.encode('utf-8') if isinstance(msg, str) else msg
        self.lw_qos = qos
        self.lw_retain = retain

    def connect(self, clean_session=True):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        addr = socket.getaddrinfo(self.server, self.port)[0][-1]
        self.sock.connect(addr)
        if not is_micropython:
            self.sock.settimeout(10)
        if self.ssl_enabled:
            # Em CPython usa ssl.wrap_socket; em MicroPython, pode ser diferente.
            self.sock = ssl.wrap_socket(self.sock, **self.ssl_params)
        # Constrói a mensagem de conexão
        premsg = bytearray(b"\x10\0\0\0\0\0")
        # Muitas implementações MicroPython usam b"\x04MQTT\x04\x02\0\0"
        # Se o broker aceitar esse formato, mantenha-o.
        msg = bytearray(b"\x04MQTT\x04\x02\0\0")
        # Calcula o tamanho: variable header (10 bytes) + payload (client_id)
        sz = 10 + 2 + len(self.client_id)
        msg[6] = (1 if clean_session else 0) << 1
        if self.user is not None:
            sz += 2 + len(self.user) + 2 + len(self.pswd)
            msg[6] |= 0xC0
        if self.keepalive:
            assert self.keepalive < 65536
            msg[7] = self.keepalive >> 8
            msg[8] = self.keepalive & 0x00FF
        if self.lw_topic:
            sz += 2 + len(self.lw_topic) + 2 + len(self.lw_msg)
            msg[6] |= 0x4 | ((self.lw_qos & 0x1) << 3) | ((self.lw_qos & 0x2) << 3)
            msg[6] |= self.lw_retain << 5

        i = 1
        while sz > 0x7f:
            premsg[i] = (sz & 0x7f) | 0x80
            sz //= 128
            i += 1
        premsg[i] = sz

        if self.verbose:
            print("Enviando CONNECT...")
        _send(self.sock, premsg[:i + 2])
        _send(self.sock, msg)
        self._send_str(self.client_id)
        if self.lw_topic:
            self._send_str(self.lw_topic)
            self._send_str(self.lw_msg)
        if self.user is not None:
            self._send_str(self.user)
            self._send_str(self.pswd)
        if self.verbose:
            print("Aguardando CONNACK...")
        resp = _recv(self.sock, 4)
        if len(resp) < 4:
            raise MQTTException("Invalid CONNACK size")
        if resp[0] != 0x20 or resp[1] != 0x02:
            raise MQTTException("Invalid CONNACK")
        if resp[3] != 0:
            raise MQTTException(resp[3])
        return resp[2] & 1

    def disconnect(self):
        _send(self.sock, b"\xe0\0")
        self.sock.close()

    def ping(self):
        _send(self.sock, b"\xc0\0")

    def publish(self, topic, msg, retain=False, qos=0):
        if isinstance(topic, str):
            topic = topic.encode('utf-8')
        if isinstance(msg, str):
            msg = msg.encode('utf-8')
        header = 0x30 | (qos << 1) | retain
        sz = 2 + len(topic) + len(msg)
        if qos > 0:
            sz += 2
        assert sz < 2097152

        length_bytes = bytearray()
        temp_sz = sz
        while temp_sz > 0x7f:
            length_bytes.append((temp_sz & 0x7f) | 0x80)
            temp_sz //= 128
        length_bytes.append(temp_sz)
        _send(self.sock, bytes([header]) + length_bytes)
        self._send_str(topic)
        if qos > 0:
            self.pid += 1
            pid = self.pid
            _send(self.sock, struct.pack("!H", pid))
        _send(self.sock, msg)
        if qos == 1:
            while True:
                op = self.wait_msg()
                if op == 0x40:
                    sz_resp = _recv(self.sock, 1)
                    if sz_resp != b"\x02":
                        raise MQTTException("Invalid PUBACK")
                    rcv_pid_bytes = _recv(self.sock, 2)
                    rcv_pid = (rcv_pid_bytes[0] << 8) | rcv_pid_bytes[1]
                    if pid == rcv_pid:
                        return
        elif qos == 2:
            raise NotImplementedError("QoS 2 não implementado")

    def subscribe(self, topic, qos=0):
        assert self.cb is not None, "Callback não definida para subscription"
        if isinstance(topic, str):
            topic = topic.encode('utf-8')
        self.pid += 1
        packet_id = self.pid
        remaining_length = 2 + 2 + len(topic) + 1
        length_bytes = bytearray()
        temp_len = remaining_length
        while temp_len > 0x7f:
            length_bytes.append((temp_len & 0x7f) | 0x80)
            temp_len //= 128
        length_bytes.append(temp_len)
        fixed_header = bytes([0x82]) + bytes(length_bytes)
        pkt = fixed_header + struct.pack("!H", packet_id)
        _send(self.sock, pkt)
        self._send_str(topic)
        _send(self.sock, qos.to_bytes(1, "big"))
        while True:
            op = self.wait_msg()
            if op == 0x90:
                resp = _recv(self.sock, 4)
                if resp[1] != (packet_id >> 8) or resp[2] != (packet_id & 0xFF):
                    raise MQTTException("Packet ID inválido no SUBACK")
                if resp[3] == 0x80:
                    raise MQTTException("Subscription falhou")
                return

    def wait_msg(self):
        res = _recv(self.sock, 1)
        self.sock.setblocking(True)
        if not res:
            return None
        if res == b"":
            raise OSError("Socket fechado")
        if res == b"\xd0":
            sz = _recv(self.sock, 1)[0]
            if sz != 0:
                raise MQTTException("Tamanho inválido no PINGRESP")
            return None
        op = res[0]
        if (op & 0xf0) != 0x30:
            return op
        remaining_length = self._recv_len()
        topic_len_bytes = _recv(self.sock, 2)
        topic_len = (topic_len_bytes[0] << 8) | topic_len_bytes[1]
        topic = _recv(self.sock, topic_len)
        remaining_length -= (topic_len + 2)
        pid = None
        if op & 0x06:
            pid_bytes = _recv(self.sock, 2)
            pid = (pid_bytes[0] << 8) | pid_bytes[1]
            remaining_length -= 2
        msg = _recv(self.sock, remaining_length)
        if self.cb:
            self.cb(topic, msg)
        if op & 0x06 == 2:
            pkt = bytearray(b"\x40\x02\0\0")
            struct.pack_into("!H", pkt, 2, pid)
            _send(self.sock, pkt)
        elif op & 0x06 == 4:
            raise NotImplementedError("QoS 2 não implementado")
        return op

    def check_msg(self):
        self.sock.setblocking(False)
        try:
            return self.wait_msg()
        except socket.error:
            return None
        finally:
            self.sock.setblocking(True)

    def sleep(self, t):
        end_time = time.time() + t
        while time.time() < end_time:
            self.check_msg()
            time.sleep(0.1)
