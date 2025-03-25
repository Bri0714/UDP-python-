import flet as ft
import socket
import threading
import queue
from dto.Midatagrama import Midatagrama
import configparser
import sys
import subprocess
import os

def Emisor(page: ft.Page):
    page.title = "CLIENTE UDP - Emisor y Receptor"
    
    # Centramos la interfaz
    page.horizontal_alignment = "center"
    page.vertical_alignment = "center"

    # ----------------------------------------------------------------------
    # 1. Leer config.ini
    # ----------------------------------------------------------------------
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    server_ip = config["CLIENT"]["server_ip"]
    server_port = int(config["CLIENT"]["server_port"])
    default_username = config["CLIENT"].get("username")  # Se usará lo configurado

    # Variable para almacenar el usuario actual (para diferenciar envíos)
    usuario_actual = default_username.strip() if default_username else ""

    # ----------------------------------------------------------------------
    # 2. TextField de solo lectura para TODOS los mensajes (locales + chat)
    # ----------------------------------------------------------------------
    txt_logs = ft.TextField(
        value="",
        multiline=True,
        width=400,
        height=250,
        read_only=True
    )

    def log_message(text: str):
        """Agrega una línea de texto a txt_logs."""
        txt_logs.value += text + "\n"
        page.update()

    # ----------------------------------------------------------------------
    # 3. Componentes de la UI (Usuario, Mensaje, Botones, etc.)
    # ----------------------------------------------------------------------
    lbl_titulo = ft.Text("CLIENTE UDP", color="red", weight="bold", size=20)

    lbl_usuario = ft.Text("Usuario:", size=16)
    txt_usuario = ft.TextField(
        label="Ingrese su usuario",
        width=350,
        value=default_username
    )

    lbl_mensaje = ft.Text("Mensaje:", size=16)
    txt_mensaje = ft.TextField(
        label="Ingrese el mensaje",
        width=350
    )

    # Variable global para almacenar la ruta del archivo seleccionado
    selected_file = None

    # ----------------------------------------------------------------------
    # 4. FilePicker para seleccionar archivo
    # ----------------------------------------------------------------------
    def on_file_picker_result(e: ft.FilePickerResultEvent):
        nonlocal selected_file
        if e.files is not None and len(e.files) > 0:
            selected_file = e.files[0].path  # ruta completa
            log_message(f"Archivo seleccionado: {os.path.basename(selected_file)}")
        else:
            selected_file = None
        page.update()

    file_picker = ft.FilePicker(on_result=on_file_picker_result)
    page.overlay.append(file_picker)

    btn_seleccionar_archivo = ft.ElevatedButton(
        "Seleccionar Archivo",
        on_click=lambda e: file_picker.pick_files(allowed_extensions=["mp3"])
    )

    # ----------------------------------------------------------------------
    # 5. Crear socket para envío y recepción
    # ----------------------------------------------------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))  # Puerto aleatorio para recibir respuestas

    # Cola para los mensajes recibidos
    mensajes_queue = queue.Queue()

    # ----------------------------------------------------------------------
    # 6. Hilo de recepción (escucha en segundo plano)
    # ----------------------------------------------------------------------
    def escuchar():
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                mensaje = data.decode('utf-8')
                mensajes_queue.put(mensaje)
            except OSError as e:
                # Error específico de Windows si se cierra el socket, etc.
                if hasattr(e, "winerror") and e.winerror == 10054:
                    continue
                else:
                    mensajes_queue.put(f"Error al recibir datagrama: {e}")
                    break

    hilo_escucha = threading.Thread(target=escuchar, daemon=True)
    hilo_escucha.start()

    # ----------------------------------------------------------------------
    # 7. Función para refrescar y mostrar los mensajes recibidos
    # ----------------------------------------------------------------------
    def refrescar_mensajes():
        while not mensajes_queue.empty():
            msg = mensajes_queue.get()
            # Aquí, en lugar de contenedores, simplemente agregamos el texto a txt_logs
            log_message(msg)
        page.update()

    # ----------------------------------------------------------------------
    # 8. Función para enviar un mensaje
    # ----------------------------------------------------------------------
    def enviar_click(e):
        usuario = txt_usuario.value.strip()
        mensaje = txt_mensaje.value.strip()

        # Validaciones
        if not usuario and not mensaje:
            log_message("Debe ingresar un usuario y un mensaje")
            return

        if not usuario:
            log_message("No has ingresado usuario, por favor intenta enviar nuevamente")
            return

        if not mensaje:
            log_message("No hay mensaje para enviar")
            return

        if not selected_file:
            log_message("Debe registrar un archivo")
            return

        if not selected_file.lower().endswith(".mp3"):
            log_message("El archivo debe tener extensión .mp3")
            return

        # Preparar contenido a enviar
        nombre_archivo = os.path.basename(selected_file)
        contenido = f"{usuario}: {mensaje}\narchivo: {nombre_archivo}"
        datagrama = Midatagrama.crear_datagrama(server_ip, server_port, contenido)

        try:
            sock.sendto(datagrama.get_bytes(), (datagrama.ip, datagrama.puerto))
            log_message("Mensaje enviado")
            txt_mensaje.value = ""
        except Exception as ex:
            log_message(f"Error al enviar: {ex}")
        finally:
            page.update()

    btn_enviar = ft.ElevatedButton("Enviar", on_click=enviar_click)

    # ----------------------------------------------------------------------
    # 9. Botón "Refrescar" para leer mensajes pendientes
    # ----------------------------------------------------------------------
    def refrescar_click(e):
        refrescar_mensajes()

    btn_refrescar = ft.ElevatedButton("Refrescar", on_click=refrescar_click)

    # ----------------------------------------------------------------------
    # 10. Disposición de la interfaz
    # ----------------------------------------------------------------------
    layout = ft.Column(
        controls=[
            lbl_titulo,
            lbl_usuario,
            txt_usuario,
            lbl_mensaje,
            txt_mensaje,
            btn_seleccionar_archivo,
            ft.Row([btn_enviar, btn_refrescar], alignment="center"),
            txt_logs  # Aquí se muestran TODOS los mensajes
        ],
        alignment="center",
        horizontal_alignment="center"
    )

    page.add(layout)

    # ----------------------------------------------------------------------
    # 11. Enviar mensaje de registro para que el servidor registre el cliente
    # ----------------------------------------------------------------------
    registro = f"{txt_usuario.value.strip()} se ha conectado"
    datagrama_registro = Midatagrama.crear_datagrama(server_ip, server_port, registro)
    try:
        sock.sendto(datagrama_registro.get_bytes(), (datagrama_registro.ip, datagrama_registro.puerto))
        log_message("Registrado en el servidor")
    except Exception as ex:
        log_message(f"Error al registrar: {ex}")

# ----------------------------------------------------------------------
# Lanzamiento automático de N clientes (desde el mismo cliente)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("config.ini")
    num_clients = int(config["APP"].get("num_clients", "1"))
    
    # Si se pasa un argumento, se entiende que es una instancia secundaria
    if len(sys.argv) > 1:
        ft.app(target=Emisor)
    else:
        # Esta instancia "maestra" lanza las demás instancias
        for i in range(1, num_clients):
            username = config["CLIENT"].get("username").strip()
            subprocess.Popen(["python", "-m", "cliente.cliente", username])
            print(f"Lanzando cliente {i+1} con username: {username}")
        ft.app(target=Emisor)
