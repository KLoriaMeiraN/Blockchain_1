"""
Executa o experimento completo SEM Docker (cada nó vira um processo local):
  1. servidor de tempo + sincronização de Cristian nos 3 nós
  2. eleição Bully, falha do líder (node3), nova eleição, retorno do node3
Gera logs/resultado.txt com tudo em ordem cronológica.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
LOGS = BASE / "logs"
LOGS.mkdir(exist_ok=True)

NODES = {1: 5001, 2: 5002, 3: 5003}
OFFSETS = {1: 2.5, 2: -1.8, 3: 0.7}
PEERS = ",".join(f"{n}=127.0.0.1:{p}" for n, p in NODES.items())


def env(**extra):
    e = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    e.update({k: str(v) for k, v in extra.items()})
    return e


def stamp(msg):
    now = time.time()
    line = f"{time.strftime('%H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d} [RUNNER] {msg}"
    print(line, flush=True)
    return line


def start_node(n, logfile):
    return subprocess.Popen([sys.executable, str(BASE / "bully.py")],
                            env=env(NODE_ID=n, PORT=NODES[n], PEERS=PEERS),
                            stdout=logfile, stderr=subprocess.STDOUT)


def main():
    out = []
    # ---------- Parte 1: Cristian
    ts = subprocess.Popen([sys.executable, str(BASE / "cristian.py"), "server"],
                          env=env(TIME_SERVER_PORT=6000))
    time.sleep(1)
    out.append("=" * 70 + "\nPARTE 1 - SINCRONIZAÇÃO DE RELÓGIOS (CRISTIAN)\n" + "=" * 70)
    for n in NODES:
        r = subprocess.run([sys.executable, str(BASE / "cristian.py"), "client"],
                           env=env(NODE_ID=n, CLOCK_OFFSET=OFFSETS[n], TIME_SERVER_PORT=6000),
                           capture_output=True, text=True, encoding="utf-8")
        print(r.stdout, end="")
        out.append(r.stdout.rstrip())
    ts.terminate()

    # ---------- Parte 2: Bully
    files = {n: open(LOGS / f"node{n}.log", "w", encoding="utf-8") for n in NODES}
    runner = []
    runner.append(stamp("subindo node1, node2, node3"))
    procs = {n: start_node(n, files[n]) for n in NODES}
    time.sleep(8)

    runner.append(stamp(">>> SIMULANDO FALHA: encerrando node3 (líder)"))
    procs[3].kill()
    time.sleep(10)

    runner.append(stamp(">>> node3 voltando"))
    procs[3] = start_node(3, files[3])
    time.sleep(8)

    runner.append(stamp("fim do experimento"))
    for p in procs.values():
        p.kill()
    for f in files.values():
        f.close()

    lines = list(runner)
    for n in NODES:
        lines += (LOGS / f"node{n}.log").read_text(encoding="utf-8").splitlines()
    lines.sort(key=lambda l: l[:12])

    out.append("\n" + "=" * 70 + "\nPARTE 2 - ELEIÇÃO DE COORDENADOR (BULLY)\n" + "=" * 70)
    out += lines
    out.append("\n" + "=" * 70 + "\nRESUMO\n" + "=" * 70)
    out.append(f"mensagens ELECTION enviadas   : {sum('-> ELECTION' in l for l in lines)}")
    out.append(f"respostas OK recebidas        : {sum('<- OK' in l for l in lines)}")
    out.append(f"mensagens COORDINATOR enviadas: {sum('-> COORDINATOR' in l for l in lines)}")
    out += [l for l in lines if "COORDENADOR =" in l or "FALHA" in l]

    text = "\n".join(out) + "\n"
    (LOGS / "resultado.txt").write_text(text, encoding="utf-8")
    print("\n".join(out[out.index("\n" + "=" * 70 + "\nPARTE 2 - ELEIÇÃO DE COORDENADOR (BULLY)\n" + "=" * 70):]))
    print(f"\nResultado salvo em {LOGS / 'resultado.txt'}")


if __name__ == "__main__":
    main()
