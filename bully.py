"""
Algoritmo do Valentão (Bully) - eleição de coordenador.

Mensagens:
  ELECTION     -> enviada aos nós de ID maior; quem está vivo responde OK
  OK           -> "estou vivo e assumo a eleição"
  COORDINATOR  -> anúncio do novo líder para todos
  HEARTBEAT    -> verificação periódica se o líder está vivo

Variáveis de ambiente:
  NODE_ID  id deste nó (inteiro)
  PORT     porta em que este nó escuta (padrão 5000)
  PEERS    lista "id=host:porta" separada por vírgula, ex.: 1=node1:5000,2=node2:5000
"""
import json
import os
import socket
import socketserver
import sys
import threading
import time

NODE_ID = int(os.environ["NODE_ID"])
PORT = int(os.getenv("PORT", "5000"))
PEERS = {}
for item in os.environ["PEERS"].split(","):
    nid, addr = item.split("=")
    host, port = addr.split(":")
    PEERS[int(nid)] = (host, int(port))
PEERS.pop(NODE_ID, None)

HEARTBEAT_INTERVAL = 2.0   # s entre heartbeats
TIMEOUT = 1.0              # s para considerar um nó sem resposta
COORD_WAIT = 4.0           # s esperando COORDINATOR depois de receber OK

leader = None
electing = False
failure_time = None
lock = threading.Lock()
print_lock = threading.Lock()
coord_event = threading.Event()


def log(msg):
    now = time.time()
    line = (f"{time.strftime('%H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d} "
            f"[node{NODE_ID}] {msg}\n")
    with print_lock:  # evita linhas misturadas entre threads
        sys.stdout.write(line)
        sys.stdout.flush()


def send(to, mtype):
    """Envia uma mensagem e devolve a resposta (ou None se o nó não responder)."""
    host, port = PEERS[to]
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as s:
            s.sendall((json.dumps({"type": mtype, "from": NODE_ID}) + "\n").encode())
            line = s.makefile().readline()
            return json.loads(line) if line else None
    except OSError:
        return None


def set_leader(nid):
    global leader, failure_time
    leader = nid
    coord_event.set()
    msg = f"*** COORDENADOR = node{nid} ***"
    if failure_time is not None:
        msg += f" (sistema recuperado em {time.time() - failure_time:.2f} s após detectar a falha)"
        failure_time = None
    log(msg)


def start_election():
    global electing
    with lock:
        if electing:
            return
        electing = True
    try:
        while True:
            coord_event.clear()
            higher = sorted(p for p in PEERS if p > NODE_ID)
            log(f"iniciando ELEIÇÃO (nós maiores: {['node%d' % p for p in higher] or 'nenhum'})")
            got_ok = False
            for p in higher:
                log(f"-> ELECTION para node{p}")
                r = send(p, "ELECTION")
                if r and r.get("type") == "OK":
                    log(f"<- OK de node{p}")
                    got_ok = True
                else:
                    log(f"x  node{p} não respondeu")
            if not got_ok:
                set_leader(NODE_ID)
                for p in sorted(PEERS):
                    log(f"-> COORDINATOR para node{p}")
                    send(p, "COORDINATOR")
                return
            log("aguardando COORDINATOR de um nó maior...")
            if coord_event.wait(COORD_WAIT):
                return
            log("timeout aguardando COORDINATOR; reiniciando eleição")
    finally:
        electing = False


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        msg = json.loads(self.rfile.readline())
        mtype, src = msg["type"], msg["from"]
        if mtype == "ELECTION":
            log(f"<- ELECTION de node{src}; -> OK")
            self.wfile.write(b'{"type": "OK"}\n')
            threading.Thread(target=start_election, daemon=True).start()
        elif mtype == "COORDINATOR":
            log(f"<- COORDINATOR de node{src}")
            self.wfile.write(b'{"type": "ACK"}\n')
            if src < NODE_ID:  # um nó menor se declarou líder: o Bully contesta
                threading.Thread(target=start_election, daemon=True).start()
            else:
                set_leader(src)
        elif mtype == "HEARTBEAT":
            self.wfile.write(b'{"type": "ALIVE"}\n')


def monitor():
    global leader, failure_time
    while True:
        time.sleep(HEARTBEAT_INTERVAL)
        if electing or leader == NODE_ID:
            continue
        if leader is None:
            start_election()
            continue
        if send(leader, "HEARTBEAT") is None:
            failure_time = time.time()
            log(f"!!! líder node{leader} não respondeu ao HEARTBEAT -> FALHA detectada")
            leader = None
            start_election()


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"nó iniciado na porta {PORT}; pares: {['node%d' % p for p in sorted(PEERS)]}")
    time.sleep(1.5)  # dá tempo dos outros nós subirem
    start_election()
    monitor()
