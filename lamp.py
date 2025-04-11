import tkinter as tk
import requests
import json
import uuid

class LampApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lâmpada Inteligente")
        self.is_on = False
        self.ae_name = f"LampAE-{uuid.uuid4().hex[:4]}"
        self.container_name = "CONT_1"
        self.cse_url = "http://localhost:8080/cse-in"

        if self.register_ae():
            self.create_container()

        # GUI
        self.canvas = tk.Canvas(self.root, width=200, height=200)
        self.canvas.pack(pady=20)
        self.lamp = self.canvas.create_oval(50, 50, 150, 150, fill="red")
        self.toggle_button = tk.Button(self.root, text="Ligar / Desligar", command=self.toggle_lamp)
        self.toggle_button.pack()

    def register_ae(self):
        headers = {
            "X-M2M-Origin": "CAdmin2",
            "X-M2M-RI": str(uuid.uuid4()),
            "X-M2M-RVI": "3",
            "Content-Type": "application/json;ty=2",
            "Accept": "application/json"
        }
        payload = {
            "m2m:ae": {
                "rn": self.ae_name,
                "api": "Napp.lightbulb",
                "rr": True,
                "srv": ["3"]
            }
        }
        try:
            response = requests.post(self.cse_url, headers=headers, data=json.dumps(payload))
            print("Registo AE:", response.status_code, response.text)
            return response.status_code in (200, 201)
        except Exception as e:
            print("Erro ao registar AE:", e)
            return False

    def create_container(self):
        headers = {
            "X-M2M-Origin": "CAdmin",
            "X-M2M-RI": str(uuid.uuid4()),
            "X-M2M-RVI": "3",
            "Content-Type": "application/json;ty=3",
            "Accept": "application/json"
        }
        payload = {
            "m2m:cnt": {
                "rn": self.container_name
            }
        }
        try:
            url = f"{self.cse_url}/{self.ae_name}"
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            print("Criação de Container:", response.status_code, response.text)
        except Exception as e:
            print("Erro ao criar container:", e)

    def send_state_to_acme(self):
        headers = {
            "X-M2M-Origin": "CAdmin",
            "X-M2M-RI": str(uuid.uuid4()),
            "X-M2M-RVI": "3",
            "Content-Type": "application/json;ty=4",
            "Accept": "application/json"
        }
        content = "on" if self.is_on else "off"
        payload = {
            "m2m:cin": {
                "con": content,
                "cnf": "text/plain:0"
            }
        }
        try:
            url = f"{self.cse_url}/{self.ae_name}/{self.container_name}"
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            print("Estado enviado:", content, "|", response.status_code)
        except Exception as e:
            print("Erro ao enviar estado:", e)

    def toggle_lamp(self):
        self.is_on = not self.is_on
        self.canvas.itemconfig(self.lamp, fill="green" if self.is_on else "red")
        self.send_state_to_acme()

if __name__ == "__main__":
    root = tk.Tk()
    app = LampApp(root)
    root.mainloop()
