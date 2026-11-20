"""
Algoritmo de Cristian - sincronização de relógios.

Uso:
  python cristian.py server   -> servidor de tempo (referência)
  python cristian.py client   -> processo que sincroniza seu relógio

Variáveis de ambiente:
  TIME_SERVER_HOST / TIME_SERVER_PORT  endereço do servidor (padrão 127.0.0.1:6000)
  NODE_ID                              identificação do nó (cliente)
  CLOCK_OFFSET                         desvio artificial do relógio local em segundos (cliente)
"""
import json
import os
import random
import socket
import socketserver
import sys
import time

HOST = os.getenv("TIME_SERVER_HOST", "127.0.0.1")
PORT = int(os.getenv("TIME_SERVER_PORT", "6000"))
ROUNDS = 5


# ---------------------------------------------------------------- servidor
class TimeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.recv(1024)
        time.sleep(random.uniform(0.01, 0.10))  # latência simulada (ida)
        server_time = time.time()
        time.sleep(random.uniform(0.01, 0.10))  # latência simulada (volta)
        self.request.sendall(json.dumps({"time": server_time}).encode())


def run_server():
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), TimeHandler) as srv:
        print(f"[TIMESERVER] servidor de tempo ouvindo na porta {PORT}", flush=True)
        srv.serve_forever()


# ---------------------------------------------------------------- cliente
def request_time():
    for _ in range(30):  # espera o servidor subir
        try:
            with socket.create_connection((HOST, PORT), timeout=5) as s:
                s.sendall(b"TIME")
                return json.loads(s.recv(1024).decode())["time"]
        except OSError:
            time.sleep(1)
    sys.exit("servidor de tempo indisponível")


def run_client():
    name = f"node{os.getenv('NODE_ID', '?')}"
    offset = float(os.getenv("CLOCK_OFFSET", "0"))  # relógio local = real + offset

    def local_clock():
        return time.time() + offset

    print(f"[{name}] ===== Sincronização de Cristian =====", flush=True)
    print(f"[{name}] desvio inicial do relógio local: {offset:+.6f} s", flush=True)

    samples = []
    for i in range(1, ROUNDS + 1):
        t0 = local_clock()
        ts = request_time()
        t1 = local_clock()
        rtt = t1 - t0
        estimated = ts + rtt / 2          # fórmula de Cristian
        adjust = estimated - t1
        samples.append((rtt, adjust))
        print(f"[{name}] rodada {i}: T0={t0:.6f} Tserv={ts:.6f} T1={t1:.6f} "
              f"RTT={rtt * 1000:7.2f} ms  ajuste={adjust:+.6f} s", flush=True)

    # usa a amostra com menor RTT (menor incerteza)
    rtt, adjust = min(samples)
    before = offset
    offset += adjust
    print(f"[{name}] melhor amostra: RTT={rtt * 1000:.2f} ms (incerteza ±{rtt * 500:.2f} ms)", flush=True)
    print(f"[{name}] diferença ANTES : {before * 1000:+10.3f} ms", flush=True)
    print(f"[{name}] diferença DEPOIS: {offset * 1000:+10.3f} ms", flush=True)
    print(f"[{name}] ======================================", flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "client"
    run_server() if mode == "server" else run_client()
