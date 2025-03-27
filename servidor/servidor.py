import flet as ft
import socket
import threading
import queue
import configparser

class ReceptorApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Servidor UDP - Receptor"
        self.page.horizontal_alignment = "center"
        self.page.vertical_alignment = "center"
        self._leer_config()
        self._crear_componentes_ui()
        self.mensajes_queue = queue.Queue()
        self.connected_clients = set()
        self.hilo_escucha = None

    def _leer_config(self):
        # 1. Lectura de config.ini
        self.config = configparser.ConfigParser()
        # Ruta absoluta a config.ini
        self.config.read(r"C:\Users\Usuario\desktop\app_udp_python\config.ini")
        print("Secciones encontradas en config.ini:", self.config.sections())
        self.server_port = int(self.config["SERVER"]["port"])
        self.max_clients = int(self.config["SERVER"].get("max_clients", "10"))

    def _crear_componentes_ui(self):
        # Etiqueta de título
        self.lbl_titulo = ft.Text(
            "SERVIDOR UDP",
            color="blue",
            weight="bold",
            size=20
        )
        # Área de texto donde se muestran los mensajes
        self.txt_mensajes = ft.TextField(
            value="",
            multiline=True,
            width=450,
            height=250,
            read_only=True
        )
        # Botón para iniciar el servidor
        self.btn_iniciar = ft.ElevatedButton("Iniciar Servidor", on_click=self.iniciar_servidor_click)
        # Botón para refrescar los mensajes pendientes
        self.btn_refrescar = ft.ElevatedButton("Refrescar", on_click=self.refrescar_click)
        # Organizar la interfaz en una columna centrada
        layout = ft.Column(
            controls=[
                self.lbl_titulo,
                self.txt_mensajes,
                ft.Row([self.btn_iniciar, self.btn_refrescar], alignment="center")
            ],
            alignment="center",
            horizontal_alignment="center"
        )
        self.page.add(layout)

    def escuchar_udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.server_port))
        
        print(f"Servidor UDP iniciado en el puerto {self.server_port}")
        self.mensajes_queue.put(("INFO", f"Servidor UDP iniciado en el puerto {self.server_port}\nEscuchando...\n"))

        while True:
            try:
                # Se utiliza un buffer mayor para recibir mensajes grandes
                data, addr = sock.recvfrom(65535)
                mensaje = data.decode('utf-8')
                
                # Registrar al cliente si aún no está en la lista
                if addr not in self.connected_clients:
                    self.connected_clients.add(addr)

                # Guardar el mensaje para mostrarlo en la interfaz
                self.mensajes_queue.put((addr, mensaje))

                # Reenviar el mensaje solo a los demás clientes
                if "se ha conectado" not in mensaje:
                    for client_addr in list(self.connected_clients):
                        if client_addr != addr:
                            try:
                                sock.sendto(data, client_addr)
                            except OSError as e:
                                print(f"No se pudo enviar a {client_addr}: {e}")
                                self.connected_clients.remove(client_addr)
            except Exception as e:
                print("Error al recibir mensaje:", e)
                self.mensajes_queue.put(("INFO", f"Error al recibir mensaje: {e}\n"))
                break

    def iniciar_servidor_click(self, e):
        """
        Función que se ejecuta al pulsar "Iniciar Servidor".
        Crea e inicia el hilo de escucha y deshabilita el botón.
        """
        if self.hilo_escucha is None:
            self.hilo_escucha = threading.Thread(target=self.escuchar_udp, daemon=True)
            self.hilo_escucha.start()
            self.btn_iniciar.disabled = True
            self.page.update()

    def refrescar_click(self, e):
        """
        Función que se ejecuta al pulsar "Refrescar".
        Lee todos los mensajes de la cola y los muestra en 'txt_mensajes',
        filtrando los mensajes de chunks (que comienzan con "FILE;") para no saturar la UI.
        """
        while not self.mensajes_queue.empty():
            addr, mensaje = self.mensajes_queue.get()
            if addr == "INFO":
                self.txt_mensajes.value += mensaje
            else:
                # Si el mensaje es de un chunk, lo ignoramos en la interfaz
                if mensaje.startswith("FILE;"):
                    # Opcional: imprimir detalles en la consola (truncado)
                    print(f"Chunk recibido de {addr}: {mensaje[:50]}...")
                else:
                    self.txt_mensajes.value += (
                        f"Remitente {addr}\n"
                        "El mensaje recibido es:\n"
                        f"{mensaje}\n"
                        "Escuchando...\n"
                    )
        self.page.update()

def main(page: ft.Page):
    ReceptorApp(page)

if __name__ == "__main__":
    ft.app(target=main)
