import socket
import threading
import sys

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000

def recv_loop(sock):
    try:
        buf = ""
        while True:
            data = sock.recv(4096)
            if not data:
                print("\nconnection closed by server")
                break
            buf += data.decode("utf-8", errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                print(line)
    except Exception:
        print("\nconnection error")
    finally:
        try:
            sock.close()
        except OSError:
            pass
        os_exit()

def os_exit():
    try:
        sys.exit(0)
    except SystemExit:
        pass

def main():
    if len(sys.argv) >= 2:
        nickname = sys.argv[1]
    else:
        nickname = input("enter nickname: ").strip() or "guest"

    host = SERVER_HOST
    port = SERVER_PORT
    if len(sys.argv) >= 3:
        host = sys.argv[2]
    if len(sys.argv) >= 4:
        port = int(sys.argv[3])

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except OSError as e:
        print("cannot connect", e)
        return

    # handshake
    sock.sendall(f"NICK {nickname}\n".encode("utf-8"))
    resp = sock.recv(4096).decode("utf-8", errors="ignore").strip()
    if resp != "OK":
        print("server refused:", resp)
        sock.close()
        return

    print("connected type /help for commands")
    t = threading.Thread(target=recv_loop, args=(sock,), daemon=True)
    t.start()

    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            sock.sendall(line.rstrip("\n").encode("utf-8") + b"\n")
            if line.strip() == "/quit":
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sock.close()
        except OSError:
            pass

if __name__ == "__main__":
    main()
