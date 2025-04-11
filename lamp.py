import tkinter as tk

class LampApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lâmpada")

        self.is_on = False  # Estado inicial: apagada

        # Canvas para desenhar a "lâmpada"
        self.canvas = tk.Canvas(self.root, width=200, height=200)
        self.canvas.pack(pady=20)

        # Desenha o círculo que representa a lâmpada
        self.lamp = self.canvas.create_oval(50, 50, 150, 150, fill="red")

        # Botão para alternar o estado da lâmpada
        self.toggle_button = tk.Button(self.root, text="Ligar / Desligar", command=self.toggle_lamp)
        self.toggle_button.pack()

    def toggle_lamp(self):
        self.is_on = not self.is_on
        new_color = "green" if self.is_on else "red"
        self.canvas.itemconfig(self.lamp, fill=new_color)

if __name__ == "__main__":
    root = tk.Tk()
    app = LampApp(root)
    root.mainloop()
