import socket
import threading
import queue
import datetime
import sys

HOST = "0.0.0.0"
PORT = 5000

# Global state
clients_by_sock = {}
clients_by_name = {}
clients_lock = threading.Lock()

class Client:
    def __init__(self, sock, addr, name):
        self.sock = sock
        self.addr = addr
        self.name = name
        self.q = queue.Queue()
        self.alive = True

def now_time():
    return datetime.datetime.now().strftime("%H:%M:%S")

def send_line(sock, text):
    try:
        sock.sendall((text + "\n").encode("utf-8"))
    except OSError:
        pass

def broadcast(from_client, text):
    with clients_lock:
        for c in list(clients_by_sock.values()):
            if c is not from_client:
                c.q.put(text)

def send_private(from_client, to_name, text):
    with clients_lock:
        target = clients_by_name.get(to_name)
    if not target:
        from_client.q.put(f"[{now_time()}] system target user not found")
        return
    target.q.put(f"[{now_time()}] private from {from_client.name}: {text}")
    if target is not from_client:
        from_client.q.put(f"[{now_time()}] private to {to_name}: {text}")

def list_users():
    with clients_lock:
        return sorted(clients_by_name.keys())

def unique_name(desired):
    base = desired
    n = 1
    with clients_lock:
        while desired in clients_by_name:
            n += 1
            desired = f"{base}{n}"
    return desired

def register_client(sock):
    # send_line(sock, "welcome please set your nickname")
    data = sock.recv(4096).decode("utf-8", errors="ignore")
    first = data.strip().splitlines()[0] if data else ""
    if not first.startswith("NICK "):
        send_line(sock, "ERROR first line must be NICK yourname")
        return None
    name = first[5:].strip()
    if not name:
        send_line(sock, "ERROR empty name")
        return None
    with clients_lock:
        if name in clients_by_name:
            send_line(sock, "ERROR name already in use")
            return None
        addr = sock.getpeername()
        c = Client(sock, addr, name)
        clients_by_sock[sock] = c
        clients_by_name[name] = c
    send_line(sock, "OK")
    msg = f"[{now_time()}] system {name} joined"
    broadcast(c, msg)
    print(msg)
    return c

def writer_loop(c: Client):
    try:
        while c.alive:
            line = c.q.get()
            send_line(c.sock, line)
    except Exception:
        pass

def close_client(c: Client):
    if not c.alive:
        return
    c.alive = False
    try:
        c.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        c.sock.close()
    except OSError:
        pass
    with clients_lock:
        clients_by_sock.pop(c.sock, None)
        if clients_by_name.get(c.name) is c:
            clients_by_name.pop(c.name, None)
    msg = f"[{now_time()}] system {c.name} left"
    broadcast(c, msg)
    print(msg)

def handle_client(sock, addr):
    sock.settimeout(600)
    c = register_client(sock)
    if not c:
        try:
            sock.close()
        except OSError:
            pass
        return

    writer = threading.Thread(target=writer_loop, args=(c,), daemon=True)
    writer.start()

    send_line(c.sock, f"[{now_time()}] system hello {c.name} type /help for help")
    try:
        buf = ""
        while c.alive:
            data = c.sock.recv(4096)
            if not data:
                break
            buf += data.decode("utf-8", errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                if line.startswith("/"):
                    handle_command(c, line)
                elif line.startswith("@"):
                    # private message
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        c.q.put(f"[{now_time()}] system empty private message")
                        continue
                    to_field, text = parts
                    to_name = to_field[1:]
                    if not to_name:
                        c.q.put(f"[{now_time()}] system target missing")
                        continue
                    send_private(c, to_name, text)
                else:
                    msg = f"[{now_time()}] {c.name}: {line}"
                    broadcast(c, msg)
    except (ConnectionResetError, ConnectionAbortedError, TimeoutError, OSError):
        pass
    finally:
        close_client(c)

def handle_command(c: Client, line: str):
    if line == "/help":
        c.q.put("commands  /list  /nick NEWNAME  /quit  send @name message for private chat")
    elif line == "/list":
        names = ", ".join(list_users())
        c.q.put(f"users  {names}")
    elif line.startswith("/nick "):
        newname = line[6:].strip()
        if not newname:
            c.q.put("system name cannot be empty")
            return
        with clients_lock:
            if newname in clients_by_name:
                c.q.put("system name already in use")
                return
            # update maps
            clients_by_name.pop(c.name, None)
            c.name = newname
            clients_by_name[c.name] = c
        c.q.put(f"system your name is now {newname}")
        broadcast(c, f"[{now_time()}] system user renamed to {newname}")
    elif line == "/quit":
        close_client(c)
    else:
        c.q.put("system unknown command try /help")

def serve():
    print(f"chat server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        while True:
            try:
                sock, addr = s.accept()
            except OSError:
                break
            threading.Thread(target=handle_client, args=(sock, addr), daemon=True).start()

if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        print("\nserver stopped")
        sys.exit(0)
