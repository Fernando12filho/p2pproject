import socket
import threading
import os, sys, time


class Node:
    def __init__(self, host, port, shared_dir):
        self.host = host
        self.port = port  # used as node_id
        self.server_socket = None
        self.shared_dir = shared_dir

        # The access to these shared data structures must be protected with a lock in multithreading
        self.peers = []  # List of connected peers (peer_id=node_id)
        # the keys of self.request_sockets are the list of connected peers
        self.response_sockets = {} # {peer_id: response_socket}
        self.request_sockets = {}  # {peer_id: request_socket}

        self.evExit = threading.Event()
        self.lock = threading.Lock()

    # Function to start the server to listen for incoming connections
    def start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Node listening on {self.host}:{self.port}")

        while not self.evExit.is_set():
            try:
                response_socket, addr = self.server_socket.accept()
                with self.lock:
                  self.response_sockets[addr[1]] = response_socket
                  self.peers.append(addr[1])
                print(f"Connection established with peer {addr[1]}")
                response_handler = threading.Thread(
                    target=self.handle_peer, args=(response_socket,)
                )
                response_handler.start()
            except TimeoutError as e:
                continue
            except OSError as e:
                if self.evExit.is_set():
                    print("Server socket closed, exiting server...")
                else:
                    print(f"Unexpected OSError: {e}")
                    raise e

        print("Server thread exiting.")
        if self.server_socket:
            self.server_socket.close()  # Ensure the server socket is closed

    # Function to handle requests from connected peers
    def handle_peer(self, response_socket):
        while not self.evExit.is_set():
            try:
                data = response_socket.recv(1024).decode()
                if not data:
                    break
                print(f"Received data: {data}")
                # Here you would handle different types of requests
                # Accept both 'SEARCH'/'SRCH' and 'REQUEST'/'REQ'
                parts = data.strip().split()
                if not parts:
                    continue

                cmd = parts[0].upper()
                if cmd in ("SEARCH", "SRCH") and len(parts) >= 2:
                    filename = parts[1]
                    files = os.listdir(self.shared_dir)
                    if filename in files:
                        # follow Task 3 sample response code 150
                        response_socket.sendall(f"150 {filename} found.".encode())
                    else:
                        response_socket.sendall(f"450 {filename} not found.".encode())

                elif cmd in ("REQUEST", "REQ") and len(parts) >= 2:
                    filename = parts[1]
                    filepath = os.path.join(self.shared_dir, filename)
                    if os.path.isfile(filepath):
                        # length-prefixed response: 40-byte header, 4-byte length, then data
                        with open(filepath, "rb") as f:
                            file_data = f.read()
                        hint = f'250 {filename} found.'
                        lhint = f'{hint:40}'  # pad/truncate to 40 bytes
                        import struct
                        data_length = len(file_data)
                        msg = lhint.encode() + struct.pack('!I', data_length) + file_data
                        response_socket.sendall(msg)
                        print(f"Response to peer (sent):  {hint} Length in bytes: {data_length}")
                    else:
                        hint = f'550 {filename} not found.'
                        lhint = f'{hint:40}'
                        response_socket.sendall(lhint.encode())
                        print(f"Response to peer:  {hint}")

            except Exception as e:
                print(f"Error handling peer: {e}")
                break
        
    def scan_peers(self):
        # Function to discover active peers in the network
        # Probe the range of ports but do NOT keep the sockets open here.
        print('Discover active peers:')
        for port in range(5000, 5010):  # Example range of ports to scan
            if port == self.port:
                continue
            print(f'Scanning peer {port}...')
            scan_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            scan_socket.settimeout(0.5)  # avoid long waits
            try:
                scan_socket.connect((self.host, port))
                print(f'Peer {port} is active.')
                scan_socket.close()
            except (socket.timeout, socket.error):
                print(f'Peer {port} is inactive.')
        return
    
    def connect_peer(self, peer_id=None):
        # Function to connect to a peer given its peer_id (port)
        print(f'Connect to peer {peer_id}:')
        hint = ''
        with self.lock:
            if peer_id in self.request_sockets:
                hint = f'Peer {peer_id} is already connected.'
            else:
                request_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    request_socket.connect((self.host, peer_id))
                    hint = f'Peer {peer_id} connected.'
                    self.request_sockets[peer_id] = request_socket
                except socket.error as e:
                    # print(f'{e=}')                     
                    hint = f'Peer {peer_id} is inactive.'
        print(hint)

    def disconnect_peer(self, peer_id):
        # Function to disconnect from a peer given its peer_id (port)
        print(f'Disconnect from peer {peer_id}:')
        hint = ''
        with self.lock:
            if peer_id not in self.request_sockets:
                hint = f'Peer {peer_id} is NOT connected.'
            else:
                try:
                    self.request_sockets[peer_id].close()
                except Exception:
                    pass
                hint = f'Peer {peer_id} disconnected.'
                self.request_sockets.pop(peer_id, None)
        print(hint)

    def search_files(self, filename):
        # Function to search for files on all connected peers
        print(f"Search for {filename} on all connected peers:")
        lost = []
        with self.lock:
            peers = list(self.request_sockets.items())

        for peer_id, s in peers:
            try:
                s.sendall(f"SRCH {filename}".encode())
                data = s.recv(1024)
                if not data:
                    print(f"Peer {peer_id} disconnected.")
                    lost.append(peer_id)
                    continue
                resp = data.decode().strip()
                # sample responses: '150 <filename> found.' or '450 <filename> not found.'
                if resp.startswith('150'):
                    print(f"{filename} found on {peer_id}")
                else:
                    print(f"{filename} not found on {peer_id}")
            except Exception as e:
                print(f"Failed to contact peer {peer_id}: {e}")
                lost.append(peer_id)

        # remove lost connections
        if lost:
            with self.lock:
                for p in lost:
                    self.request_sockets.pop(p, None)
        return

    def request_files(self, peer_id, filename):
        # Function to request/download files from a specific peer
        if peer_id in self.request_sockets:
            s = self.request_sockets[peer_id]
            try:
                # send request
                s.sendall(f"REQ {filename}".encode())

                # receive 40-byte response header
                header = self.recvall_socket(s, 40)
                if header[:3] == b'250':
                    # read 4-byte length
                    prefix = self.recvall_socket(s, 4)
                    import struct
                    data_length = struct.unpack('!I', prefix)[0]
                    # read file data
                    filedata = self.recvall_socket(s, data_length)

                    dest_path = os.path.join(self.shared_dir, filename)
                    with open(dest_path, 'wb') as f:
                        f.write(filedata)
                    try:
                        msg = header.decode().strip()
                    except Exception:
                        msg = ''
                    print(f"{msg[4:]} on {peer_id}. {data_length} bytes received.")
                else:
                    try:
                        print(header.decode().strip())
                    except Exception:
                        print('Unknown response from peer')
            except Exception as e:
                print(f"Failed to request file from peer {peer_id}: {e}")
        else:
            print(f"No connection found for peer {peer_id}")
        pass
        
    

    # Function to run the console for interaction
    def console(self):
        while True:
            commands = input(">:").strip().split()

            # === Task 1: describe the usage of each command ===
            if (not commands) or (commands[0] == "help") or (commands[0] == "?"):
                print("show usages of all commands")
                print(" scan                     : Discover active peers.")
                print(" lp                      : List connected peers.")
                print(" connect                 : Connect to a peer.")
                print(" disconnect              : Disconnect from a peer.")
                print(" sf <filename>          : Search for a file on all connected peers.")
                print(" request <peer_id> <filename> : Request a file from a peer.")
                print(" quit                    : Quit the program.")

            # === Task 2: discover active peers and list connected peers ===
            elif commands[0] == "scan": # discover active peers
                if len(commands) == 1:
                    print("Scanning for active peers...")
                    self.scan_peers()
                else:
                    print("Usage: scan")
                
            elif commands[0] == "lp":  # list peers
                if len(commands) != 1:
                    print("Usage: lp")
                else:
                    print('List connected peers:')
                    with self.lock:
                        if not self.request_sockets:
                            print(f'Node {self.port} has no connected peers.')
                        else:
                            print(f'Node {self.port} has connected peers: ', end='')
                            for p in self.request_sockets:
                                print(f'{p} ', end='')
                            print()


            # === handle peer connection and disconnection ===
            elif commands[0] == "connect":  # connect peer_id
                if len(commands) != 2:
                    print("Usage: connect <peer_id>")
                else:
                    peer_id = int(commands[1])
                    self.connect_peer(peer_id)
                
            elif commands[0] == "disconnect":  # disconnect peer_id
                if len(commands) != 2:
                    print("Usage: disconnect")
                else:
                    peer_id = int(commands[1])
                    self.disconnect_peer(peer_id)

            # === Task 3: search for files on all connected peers ===
            elif commands[0] == "sf":  # search for files
                if len(commands) < 2:
                    print("Usage: sf <filename>")
                else:
                    filename = commands[1]
                    print(f"Searching for file: {filename}")
                    self.search_files(filename)

            # === Task 4: download files ===
            elif commands[0] == "request":  # request filename on peer_id
                if len(commands) < 3:
                    print("Usage: request <peer_id> <filename>")
                else:
                    peer_id = int(commands[1])
                    filename = commands[2]
                    self.request_files(peer_id, filename)

            elif commands[0] == "quit":
                self.evExit.set()  # Signal the server to stop
                break
            else:
                print("Unknown command.")

        # After the loop, close the server socket explicitly
        try:
            if self.server_socket:
                self.server_socket.close()  # Close the server socket to interrupt accept()
                time.sleep(0.1)
        except Exception as e:
            print(f"Error closing server socket: {e}")

        # Close all response and request sockets
        for svk, svv in self.response_sockets.items():
            svv.close()
        for sck, scv in self.request_sockets.items():
            scv.close()

    # helper to receive exact length from a socket (not using peer_id)
    def recvall_socket(self, sock, length):
        blocks = []
        remaining = length
        while remaining:
            block = sock.recv(remaining)
            if not block:
                raise EOFError(f'socket closed with {remaining} bytes left')
            blocks.append(block)
            remaining -= len(block)
        return b''.join(blocks)

        print("All sockets closed. Exiting program.")


# Main execution
if __name__ == "__main__":
    host = "127.0.0.1"  # We use the loopback address for testing
    port = int(input("Enter your port (e.g., 5000, 5001, etc.): "))

    shared_dir = f"./sf{port}"  # Directory containing shared files
    os.makedirs(shared_dir, exist_ok=True)

    peer = Node(host, port, shared_dir)

    # Start the server in a separate thread
    server_thread = threading.Thread(target=peer.start_server, daemon=True)
    server_thread.start()

    # Start the request interaction
    peer.console()

    # Wait for the server thread to finish
    server_thread.join(0.1)
    sys.exit(0)