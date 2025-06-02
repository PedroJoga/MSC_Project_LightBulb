import tkinter as tk
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import json
import socket
import time
from zeroconf import ServiceInfo, Zeroconf, NonUniqueNameException
import atexit
import signal
import sys
import uuid

ACME_SERVER_URL = "http://localhost:8081/cse-in"
DOCKER_HOST = "host.docker.internal"  # Docker host IP address
APPLICATION_ENTITY_NAME = "Light-Bulb"
CONTAINER_NAME = "Is-On"
ORIGINATOR = "CAdmin2"

NOTIFICATION_SERVER_PORT = 3000

MDNS_SERVICE_TYPE = "_http._tcp.local."
MDNS_SERVICE_NAME = f"LAMP_{str(uuid.uuid1())}" + "._http._tcp.local."
MDNS_SERVICE_PORT = 8081  # your ACME oneM2M broker port
MDNS_SERVICE_DESC = {'path': '/'}  # optional TXT records

# Estado global da lâmpada
lamp_state = {"on": False}

# Global variables for cleanup
zeroconf = None
info = None
server = None
app_event = None
root = None
cleanup_done = False

def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
    s.close()   
    return local_ip

def cleanup():
    global zeroconf, info, server, root, cleanup_done
    
    # Prevent multiple cleanup calls
    if cleanup_done:
        return
    cleanup_done = True
    
    print("Cleaning up...")
    
    # Stop the HTTP server
    if server:
        print("Shutting down HTTP server...")
        try:
            server.shutdown()
            server.server_close()
            server = None
        except Exception as e:
            print(f"Error shutting down server: {e}")
    
    # Close Tkinter window first
    if root:
        try:
            root.quit()
            root.destroy()
            root = None
        except Exception as e:
            print(f"Error closing GUI: {e}")
    
    # Unregister mDNS service
    if zeroconf and info:
        print("Unregistering mDNS service...")
        try:
            zeroconf.unregister_service(info)
            time.sleep(0.1)  # Give it a moment to unregister
            zeroconf.close()
            zeroconf = None
            info = None
            print("mDNS service unregistered")
        except Exception as e:
            print(f"Error unregistering mDNS: {e}")

def signal_handler(signum, frame):
    print(f"\nReceived signal {signum}. Shutting down gracefully...")
    cleanup()
    sys.exit(0)

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

    try:
        zeroconf.register_service(info)
    except NonUniqueNameException as e:
        print("WARNING: couldn't register mDNS because found already registered mDNS service")

    print(f"Registered mDNS service {MDNS_SERVICE_NAME} at {resolved_ip}:{MDNS_SERVICE_PORT}")

class LampHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers['Content-Length'], 0)
        data = self.rfile.read(length)

        try:
            data = json.loads(data.decode('utf-8'))
            print("Received notification:", data)
            value = bool(data["m2m:sgn"]["nev"]["rep"]["m2m:cin"]["con"])
            print("Received notification:", value)
            # change the state of the lamp
            lamp_state["on"] = value
            if app_event:
                app_event.set()
        except Exception as e:
            print("Erro ao decodificar JSON:", e)

        self.send_response(200)
        self.send_header('X-M2M-RSC', '2000')
        ri = self.headers.get('X-M2M-RI', '')
        self.send_header('X-M2M-RI', ri)
        self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default HTTP server logging
        pass
        
def start_server() -> None:
    global server
    server = HTTPServer(('localhost', NOTIFICATION_SERVER_PORT), LampHandler)
    print(f"Notification server started: Listening on {NOTIFICATION_SERVER_PORT}")

    threading.Thread(target=create_subscription_request, daemon=True).start()

    try:
        server.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")

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
    initial_satus = False
    headers = {
        "X-M2M-Origin": ORIGINATOR,
        "X-M2M-RI": "123",
        "X-M2M-RVI": "3",
        "Content-Type": "application/json;ty=4",
        "Accept": "application/json"
    }
    payload = {
        "m2m:cin": {
            "con": initial_satus,
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
            "nu": [f"http://{DOCKER_HOST}:{NOTIFICATION_SERVER_PORT}"],
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
    global app_event, root

    root = tk.Tk()
    root.title("Lâmpada")
    
    # Handle window close event
    def on_closing():
        print("Window closing...")
        cleanup()
        # Don't call sys.exit() here, let mainloop() end naturally
    
    root.protocol("WM_DELETE_WINDOW", on_closing)

    canvas = tk.Canvas(root, width=200, height=200, bg="white")
    canvas.pack()

    # Desenha a lâmpada como um círculo
    lamp = canvas.create_oval(50, 50, 150, 150, fill="black", outline="gray", width=2)

    def check_event():
        try:
            if app_event and app_event.is_set():
                update_lamp(canvas, lamp)
                app_event.clear()
            root.after(100, check_event)
        except tk.TclError:
            # Window has been destroyed
            pass

    root.after(100, check_event)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        # Only cleanup if not already done
        if not cleanup_done:
            cleanup()

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Don't register atexit cleanup since we handle it manually
    
    try:
        if not check_application_entity_exists():
            if not create_application_entiry_request():
                sys.exit(1)
        if not create_container_request() or not set_initial_status_request():
            sys.exit(1)

        register_service()

        app_event = threading.Event()
        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        # Start GUI loop
        gui_loop()

    except KeyboardInterrupt:
        print("\nKeyboard interrupt received")
        cleanup()
    except Exception as e:
        print(f"Unexpected error occurred: {e}", file=sys.stderr)
        cleanup()
    finally:
        # Final cleanup only if not already done
        if not cleanup_done:
            cleanup()
        sys.exit(0)