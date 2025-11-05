import threading
import time
import os
from p2p0 import Node

HOST = "127.0.0.1"
PORTS = [5000, 5003, 5005, 5009]

nodes = {}
threads = []

# function to run a node server in background
def start_node(port):
    node = Node(HOST, port, f"./sf{port}")
    nodes[port] = node
    t = threading.Thread(target=node.start_server, daemon=True)
    t.start()
    import threading
    import time
    import os
    from p2p0 import Node

    HOST = "127.0.0.1"
    PORTS = [5000, 5003, 5005, 5009]

    nodes = {}
    threads = []

    # function to run a node server in background
    def start_node(port):
        node = Node(HOST, port, f"./sf{port}")
        nodes[port] = node
        t = threading.Thread(target=node.start_server, daemon=True)
        t.start()
        return node, t

    # Start all nodes
    for p in PORTS:
        os_thread = start_node(p)
        threads.append(os_thread[1])

    # give servers time to start
    time.sleep(0.5)

    # prepare sample shared files: put a placeholder file SkyShip.jpg in nodes 5003 and 5009
    os.makedirs('./sf5003', exist_ok=True)
    os.makedirs('./sf5009', exist_ok=True)
    with open('./sf5003/SkyShip.jpg', 'wb') as f:
        f.write(b'This is a placeholder for SkyShip.jpg on 5003')
    with open('./sf5009/SkyShip.jpg', 'wb') as f:
        f.write(b'This is a placeholder for SkyShip.jpg on 5009')

    # Use node 5000 to demo commands programmatically
    master = nodes[5000]
    print(f"--- Demo: node {master.port} scanning peers ---")
    master.scan_peers()

    print(f"--- Demo: node {master.port} connecting to 5003, 5005, 5009 ---")
    master.connect_peer(5003)
    time.sleep(0.1)
    master.connect_peer(5005)
    time.sleep(0.1)
    master.connect_peer(5009)
    time.sleep(0.2)

    print("--- Demo: list peers (lp) ---")
    with master.lock:
        if not master.request_sockets:
            print(f'Node {master.port} has no connected peers.')
        else:
            print(f'Node {master.port} has connected peers: ', end='')
            for p in master.request_sockets:
                print(f'{p} ', end='')
            print()

    print('--- Demo: search for SkyShip.jpg from node 5000 ---')
    master.search_files('SkyShip.jpg')

    print('--- Demo: disconnect 5003 ---')
    master.disconnect_peer(5003)

    print('--- Demo: list peers after disconnect ---')
    with master.lock:
        if not master.request_sockets:
            print(f'Node {master.port} has no connected peers.')
        else:
            print(f'Node {master.port} has connected peers: ', end='')
            for p in master.request_sockets:
                print(f'{p} ', end='')
            print()

    # cleanup
    for n in nodes.values():
        n.evExit.set()

    time.sleep(0.1)
    print('Demo finished.')
