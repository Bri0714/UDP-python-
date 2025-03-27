import flet as ft
import socket
import threading
import queue
from dto.Midatagrama import Midatagrama
import configparser
import sys
import subprocess
import os
import base64
import shutil
import atexit

class EmisorApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.file_transfers = {}  # Diccionario para almacenar chunks de archivos
        self._inicializar_config()
        self._configurar_directorio_cliente()
        self._configurar_page()
        self._crear_componentes_ui()
        self._crear_socket_y_hilo()
        self._registrar_cliente()

    def _inicializar_config(self):
        # 1. Leer config.ini
        self.config = configparser.ConfigParser()
        self.config.read("config.ini")
        self.server_ip = self.config["CLIENT"]["server_ip"]
        self.server_port = int(self.config["CLIENT"]["server_port"])
        default_username = self.config["CLIENT"].get("username")
        self.usuario_actual = default_username.strip() if default_username else ""

    def _configurar_directorio_cliente(self):
        # 2. Configuración y creación del directorio del cliente
        BASE_CLIENT_DIR = r"C:\Users\Usuario\Desktop\app_udp_python\cliente"
        if len(sys.argv) > 1:
            client_number = sys.argv[1]
        else:
            client_number = "1"
        self.CLIENT_ID = f"cliente no {client_number}"
        self.client_dir = os.path.join(BASE_CLIENT_DIR, self.CLIENT_ID)
        os.makedirs(self.client_dir, exist_ok=True)
        # Registrar la función de limpieza al salir de la aplicación
        atexit.register(self.cleanup)

    def cleanup(self):
        try:
            if os.path.exists(self.client_dir):
                shutil.rmtree(self.client_dir)
                print(f"Carpeta {self.client_dir} eliminada.")
        except Exception as ex:
            print(f"Error al eliminar la carpeta: {ex}")

    def _configurar_page(self):
        # Configuración de la página
        self.page.title = "CLIENTE UDP - Emisor y Receptor"
        self.page.horizontal_alignment = "center"
        self.page.vertical_alignment = "center"
        self.page.on_close = self.on_close

    def on_close(self, e):
        self.cleanup()

    def _crear_componentes_ui(self):
        # 3. TextField de solo lectura para TODOS los mensajes
        self.txt_logs = ft.TextField(
            value="",
            multiline=True,
            width=400,
            height=250,
            read_only=True
        )

        # 4. Componentes de la UI (Usuario, Mensaje, Botones, etc.)
        self.lbl_titulo = ft.Text("CLIENTE UDP", color="red", weight="bold", size=20)
        self.lbl_usuario = ft.Text("Usuario:", size=16)
        self.txt_usuario = ft.TextField(
            label="Ingrese su usuario",
            width=350,
            value=self.config["CLIENT"].get("username")
        )
        self.lbl_mensaje = ft.Text("Mensaje:", size=16)
        self.txt_mensaje = ft.TextField(
            label="Ingrese el mensaje",
            width=350
        )
        self.selected_file = None

        # 5. FilePicker para seleccionar archivo
        self.file_picker = ft.FilePicker(on_result=self.on_file_picker_result)
        self.page.overlay.append(self.file_picker)
        self.btn_seleccionar_archivo = ft.ElevatedButton(
            "Seleccionar Archivo",
            on_click=self.file_picker_click
        )
        self.btn_enviar = ft.ElevatedButton("Enviar", on_click=self.enviar_click)
        self.btn_refrescar = ft.ElevatedButton("Refrescar", on_click=self.refrescar_click)

        # Disposición de la interfaz
        layout = ft.Column(
            controls=[
                self.lbl_titulo,
                self.lbl_usuario,
                self.txt_usuario,
                self.lbl_mensaje,
                self.txt_mensaje,
                self.btn_seleccionar_archivo,
                ft.Row([self.btn_enviar, self.btn_refrescar], alignment="center"),
                self.txt_logs  # Aquí se muestran TODOS los mensajes
            ],
            alignment="center",
            horizontal_alignment="center"
        )
        self.page.add(layout)

    def _crear_socket_y_hilo(self):
        # 6. Crear socket para envío y recepción
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", 0))  # Puerto aleatorio para recibir respuestas

        # Cola para los mensajes recibidos
        self.mensajes_queue = queue.Queue()

        # 7. Hilo de recepción (escucha en segundo plano)
        self.hilo_escucha = threading.Thread(target=self.escuchar, daemon=True)
        self.hilo_escucha.start()

    def _registrar_cliente(self):
        # 13. Enviar mensaje de registro para que el servidor registre el cliente
        registro = f"{self.txt_usuario.value.strip()} se ha conectado"
        datagrama_registro = Midatagrama.crear_datagrama(self.server_ip, self.server_port, registro)
        try:
            self.sock.sendto(datagrama_registro.get_bytes(), (datagrama_registro.ip, datagrama_registro.puerto))
            self.log_message("Registrado en el servidor")
        except Exception as ex:
            self.log_message(f"Error al registrar: {ex}")

    def log_message(self, text: str):
        """Agrega una línea de texto a txt_logs."""
        self.txt_logs.value += text + "\n"
        self.page.update()

    def on_file_picker_result(self, e: ft.FilePickerResultEvent):
        if e.files is not None and len(e.files) > 0:
            self.selected_file = e.files[0].path  # ruta completa
            self.log_message(f"Archivo seleccionado: {os.path.basename(self.selected_file)}")
        else:
            self.selected_file = None
        self.page.update()

    def file_picker_click(self, e):
        self.file_picker.pick_files()

    def escuchar(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(65535)  # Buffer aumentado
                mensaje = data.decode('utf-8')
                self.mensajes_queue.put(mensaje)
            except OSError as e:
                if hasattr(e, "winerror") and e.winerror == 10054:
                    continue
                else:
                    self.mensajes_queue.put(f"Error al recibir datagrama: {e}")
                    break

    def process_file_chunk(self, msg: str):
        """
        Procesa mensajes que comienzan con "FILE;" con el formato:
        FILE;usuario;nombreArchivo;chunk_index;last_flag;chunk_b64
        Al recibir el último chunk se reensambla el archivo en la carpeta del cliente.
        """
        try:
            parts = msg.split(";", 5)
            if len(parts) < 6:
                self.log_message("Formato de file_msg incorrecto")
                return
            _, sender, filename, chunk_index_str, last_flag, chunk_b64 = parts
            chunk_index = int(chunk_index_str)
            key = (sender, filename)
            if key not in self.file_transfers:
                self.file_transfers[key] = {'chunks': {}, 'last_index': None}
            self.file_transfers[key]['chunks'][chunk_index] = chunk_b64
            if last_flag == "1":
                self.file_transfers[key]['last_index'] = chunk_index
            # Verifica si se han recibido todos los chunks
            ft_entry = self.file_transfers[key]
            if ft_entry['last_index'] is not None:
                expected_chunks = ft_entry['last_index'] + 1
                if len(ft_entry['chunks']) == expected_chunks:
                    chunks_ordered = [ft_entry['chunks'][i] for i in range(expected_chunks)]
                    file_data = b"".join(base64.b64decode(chunk) for chunk in chunks_ordered)
                    ruta_archivo = os.path.join(self.client_dir, filename)
                    with open(ruta_archivo, "wb") as f:
                        f.write(file_data)
                    self.log_message(f"Archivo {filename} recibido completo en {self.client_dir}")
                    del self.file_transfers[key]
        except Exception as ex:
            self.log_message(f"Error al procesar chunk de archivo: {ex}")

    def refrescar_mensajes(self):
        while not self.mensajes_queue.empty():
            msg = self.mensajes_queue.get()
            if msg.startswith("FILE;"):
                self.process_file_chunk(msg)
            else:
                self.log_message(msg)
        self.page.update()

    def enviar_click(self, e):
        usuario = self.txt_usuario.value.strip()
        mensaje = self.txt_mensaje.value.strip()

        # Validaciones
        if not usuario and not mensaje:
            self.log_message("Debe ingresar un usuario y un mensaje")
            return

        if not usuario:
            self.log_message("No has ingresado usuario, por favor intenta enviar nuevamente")
            return

        if not mensaje:
            self.log_message("No hay mensaje para enviar")
            return

        if not self.selected_file:
            self.log_message("Debe registrar un archivo")
            return

        if not self.selected_file.lower().endswith(".mp3"):
            self.log_message("El archivo debe tener extensión .mp3")
            return

        # Enviar primer mensaje de texto con el mensaje y nombre del archivo
        contenido = f"{usuario}: {mensaje}\narchivo: {os.path.basename(self.selected_file)}"
        datagrama = Midatagrama.crear_datagrama(self.server_ip, self.server_port, contenido)
        try:
            self.sock.sendto(datagrama.get_bytes(), (datagrama.ip, datagrama.puerto))
            self.log_message("Mensaje y archivo enviado")
            self.txt_mensaje.value = ""
        except Exception as ex:
            self.log_message(f"Error al enviar mensaje: {ex}")

        # Enviar el archivo en chunks
        chunk_size = 1024  # Tamaño del chunk
        try:
            with open(self.selected_file, "rb") as f:
                chunk_index = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunk_b64 = base64.b64encode(chunk).decode('utf-8')
                    last_flag = "1" if len(chunk) < chunk_size else "0"
                    file_msg = f"FILE;{usuario};{os.path.basename(self.selected_file)};{chunk_index};{last_flag};{chunk_b64}"
                    datagrama_file = Midatagrama.crear_datagrama(self.server_ip, self.server_port, file_msg)
                    self.sock.sendto(datagrama_file.get_bytes(), (datagrama_file.ip, datagrama_file.puerto))
                    print(f"Enviado chunk {chunk_index} (last: {last_flag})")
                    chunk_index += 1
        except Exception as ex:
            self.log_message(f"Error al enviar archivo: {ex}")
        finally:
            self.page.update()

    def refrescar_click(self, e):
        self.refrescar_mensajes()

def main(page: ft.Page):
    EmisorApp(page)

if __name__ == "__main__":
    # Esta parte maneja el lanzamiento de múltiples instancias de clientes
    config = configparser.ConfigParser()
    config.read("config.ini")
    num_clients = int(config["APP"].get("num_clients", "1"))

    # Si se pasa un argumento se entiende que es una instancia secundaria
    if len(sys.argv) > 1:
        ft.app(target=main)
    else:
        # Esta instancia "maestra" lanza las demás instancias
        for i in range(1, num_clients):
            username = config["CLIENT"].get("username").strip()
            subprocess.Popen(["python", "-m", "cliente.cliente", str(i+1)])
            print(f"Lanzando cliente {i+1} con username: {username}")
        ft.app(target=main)
