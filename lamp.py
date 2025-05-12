import tkinter as tk
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import socket
import time
from zeroconf import ServiceInfo, Zeroconf
import atexit
import signal
import sys

ACME_SERVER_URL = "http://localhost:8081/cse-in"
IS_ACME_SERVER_RUNNING_IN_DOCKER = True  # Set to True if running acme in Docker
APPLICATION_ENTITY_NAME = "Light-Bulb"
CONTAINER_NAME = "Is-On"
ORIGINATOR = "CAdmin2"

NOTIFICATION_SERVER_PORT = 3000

MDNS_SERVICE_TYPE = "_http._tcp.local."
MDNS_SERVICE_NAME = "ACME-oneM2M._http._tcp.local."
MDNS_SERVICE_PORT = 8081  # your ACME oneM2M broker port
MDNS_SERVICE_DESC = {'path': '/'}  # optional TXT records

# Estado global da lâmpada
lamp_state = {"on": False}


zeroconf = None
info = None

def get_local_ip() -> str:
    if IS_ACME_SERVER_RUNNING_IN_DOCKER:
        return "host.docker.internal"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()   
    return local_ip

def cleanup():
    global zeroconf, info
    if zeroconf and info:
        print("Unregistering mDNS service...")
        zeroconf.unregister_service(info)
        zeroconf.close()
        print("mDNS service unregistered")

def register_service():
    global zeroconf, info

    zeroconf = Zeroconf()
    ip_str = get_local_ip()
    try:
        resolved_ip = socket.gethostbyname(ip_str)
        ip_bytes = socket.inet_aton(resolved_ip)
    except Exception as e:
        raise RuntimeError(f"Could not resolve IP for '{ip_str}': {e}")

    info = ServiceInfo(
        MDNS_SERVICE_TYPE,
        MDNS_SERVICE_NAME,
        addresses=[ip_bytes],
        port=MDNS_SERVICE_PORT,
        properties=MDNS_SERVICE_DESC,
        server=f"{socket.gethostname()}.local."
    )

    zeroconf.register_service(info)
    print(f"Registered mDNS service {MDNS_SERVICE_NAME} at {resolved_ip}:{MDNS_SERVICE_PORT}")

    # Register cleanup handlers
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))


class LampHandler(BaseHTTPRequestHandler):
    def do_POST(self):

        length = int(self.headers['Content-Length'], 0)
        data = self.rfile.read(length)

        try:
            data = json.loads(data.decode('utf-8'))
            value = bool(data["m2m:sgn"]["nev"]["rep"]["m2m:cin"]["con"])
            # change the state of the lamp
            lamp_state["on"] = value
            app_event.set()
        except:
            print("Erro ao decodificar JSON:")

        self.send_response(200)
        self.send_header('X-M2M-RSC', '2000')
        ri = self.headers['X-M2M-RI']
        self.send_header('X-M2M-RI', ri)
        self.end_headers()
        
def start_server() -> None:
    server = HTTPServer(('localhost', NOTIFICATION_SERVER_PORT), LampHandler)
    print(f"Notification server started: Listening on {NOTIFICATION_SERVER_PORT}")

    threading.Thread(target=create_subscription_request, daemon=True).start()

    server.serve_forever()

def check_application_entity_exists() -> bool:
    headers = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": "123",
        "X-M2M-RVI": "3",
        "Accept": "application/json"
    }
    try:
        url = f"{ACME_SERVER_URL}?fu=1&ty=2"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            if APPLICATION_ENTITY_NAME in response.text:
                return True
        return False
    except Exception as e:
        print("Error verifying application entity", e)
    return False

def create_application_entiry_request() -> bool:
    headers = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": "123",
        "X-M2M-RVI": "3",
        "Content-Type": "application/json;ty=2",
        "Accept": "application/json"
    }
    payload = {
        "m2m:ae": {
            "rn": APPLICATION_ENTITY_NAME,
            "api": "Napp.lightbulb",
            "rr": True,
            "srv": ["3"]
        }
    }
    try:
        response = requests.post(ACME_SERVER_URL, headers=headers, data=json.dumps(payload))
        print("Registo AE:", response.status_code, response.text)
        return response.status_code in (200, 201)
    except Exception as e:
        print("Erro ao registar AE:", e)
        return False

def create_container_request() -> bool:
    headers = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": "123",
        "X-M2M-RVI": "3",
        "Content-Type": "application/json;ty=3",
        "Accept": "application/json"
    }
    payload = {
        "m2m:cnt": {
            "rn": CONTAINER_NAME
        }
    }
    try:
        url = f"{ACME_SERVER_URL}/{APPLICATION_ENTITY_NAME}"
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print("Criação de Container:", response.status_code, response.text)
        return response.status_code in (200, 201, 409)
    except Exception as e:
        print("Erro ao criar container:", e)
        return False

def set_initial_status_request() -> bool:
    headers = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": "123",
        "X-M2M-RVI": "3",
        "Content-Type": "application/json;ty=4",
        "Accept": "application/json"
    }
    payload = {
        "m2m:cin": {
            "con": "false",
            "cnf": "text/plain:0"
        }
    }

    try:
        url = f"{ACME_SERVER_URL}/{APPLICATION_ENTITY_NAME}/{CONTAINER_NAME}"
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print("Define light bulb initial status:", response.status_code, response.text)
        return response.status_code in (200, 201)
    except Exception as e:
        print("Error to define initial status:", e)
        return False

def create_subscription_request() -> bool:
    local_ip = get_local_ip()

    headers = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": "123",
        "X-M2M-RVI": "3",
        "Content-Type": "application/json;ty=23",
        "Accept": "application/json"
    }
    payload = {
        "m2m:sub": {
            "rn": "Subscription",
            "nu": [f"http://{local_ip}:{NOTIFICATION_SERVER_PORT}"],
            "nct": 1,
            "enc": {
                "net": [1, 2, 3, 4]
            } 
        }
    }

    time.sleep(1)
    # try 3 times
    for i in range(3):
        try:
            url = f"{ACME_SERVER_URL}/{APPLICATION_ENTITY_NAME}/{CONTAINER_NAME}"
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            print("Create subscription:", response.status_code, response.text)
            return response.status_code in (200, 201, 409)
        except Exception as e:
            print("Error to create subscription:", e)
        time.sleep(1)

    return False

def update_lamp(canvas, lamp) -> None:
    if lamp_state["on"]:
        canvas.itemconfig(lamp, fill="yellow", outline="orange", width=4)
    else:
        canvas.itemconfig(lamp, fill="black", outline="gray", width=2)

def gui_loop() -> None:
    global app_event

    root = tk.Tk()
    root.title("Lâmpada")

    canvas = tk.Canvas(root, width=200, height=200, bg="white")
    canvas.pack()

    # Desenha a lâmpada como um círculo
    lamp = canvas.create_oval(50, 50, 150, 150, fill="black", outline="gray", width=2)

    def check_event():
        if app_event.is_set():
            update_lamp(canvas, lamp)
            app_event.clear()
        root.after(100, check_event)

    root.after(100, check_event)
    root.mainloop()

if __name__ == "__main__":

    if not check_application_entity_exists():
        if not create_application_entiry_request():
            exit()
    if not create_container_request() or not set_initial_status_request():
        exit()

    register_service()

    app_event = threading.Event()
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # start gui
    gui_loop()
