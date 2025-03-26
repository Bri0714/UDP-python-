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

# Diccionario para ir almacenando los chunks de archivos recibidos.
# La llave es una tupla (sender, filename)
file_transfers = {}

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
    # 2. Configuración y creación del directorio del cliente
    # ----------------------------------------------------------------------
    BASE_CLIENT_DIR = r"C:\Users\Usuario\Desktop\app_udp_python\cliente"
    # Se utiliza el argumento de línea de comandos para definir el número de cliente.
    # Si no se pasa argumento, se usa "1" por defecto.
    if len(sys.argv) > 1:
        client_number = sys.argv[1]
    else:
        client_number = "1"
    CLIENT_ID = f"cliente no {client_number}"
    client_dir = os.path.join(BASE_CLIENT_DIR, CLIENT_ID)
    os.makedirs(client_dir, exist_ok=True)

    def cleanup():
        try:
            if os.path.exists(client_dir):
                shutil.rmtree(client_dir)
                print(f"Carpeta {client_dir} eliminada.")
        except Exception as ex:
            print(f"Error al eliminar la carpeta: {ex}")

    # Registrar la función de limpieza al salir de la aplicación
    atexit.register(cleanup)
    def on_close(e):
        cleanup()
    page.on_close = on_close

    # ----------------------------------------------------------------------
    # 3. TextField de solo lectura para TODOS los mensajes (locales + chat)
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
    # 4. Componentes de la UI (Usuario, Mensaje, Botones, etc.)
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
    # 5. FilePicker para seleccionar archivo
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
        on_click=lambda e: file_picker.pick_files()
    )

    # ----------------------------------------------------------------------
    # 6. Crear socket para envío y recepción
    # ----------------------------------------------------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))  # Puerto aleatorio para recibir respuestas

    # Cola para los mensajes recibidos
    mensajes_queue = queue.Queue()

    # ----------------------------------------------------------------------
    # 7. Hilo de recepción (escucha en segundo plano)
    # ----------------------------------------------------------------------
    def escuchar():
        while True:
            try:
                # Se aumenta el buffer para soportar mensajes más grandes
                data, addr = sock.recvfrom(65535)# por defecto 1024
                mensaje = data.decode('utf-8')
                mensajes_queue.put(mensaje)
            except OSError as e:
                if hasattr(e, "winerror") and e.winerror == 10054:
                    continue
                else:
                    mensajes_queue.put(f"Error al recibir datagrama: {e}")
                    break

    hilo_escucha = threading.Thread(target=escuchar, daemon=True)
    hilo_escucha.start()

    # ----------------------------------------------------------------------
    # 8. Función para procesar los _chunks_ de archivo recibidos
    # ----------------------------------------------------------------------
    def process_file_chunk(msg: str):
        """
        Procesa mensajes que comienzan con "FILE;" con el formato:
        FILE;usuario;nombreArchivo;chunk_index;last_flag;chunk_b64
        Al recibir el último _chunk_ se reensambla el archivo en la carpeta del cliente.
        """
        try:
            parts = msg.split(";", 5)
            if len(parts) < 6:
                log_message("Formato de file_msg incorrecto")
                return
            _, sender, filename, chunk_index_str, last_flag, chunk_b64 = parts
            chunk_index = int(chunk_index_str)
            key = (sender, filename)
            if key not in file_transfers:
                file_transfers[key] = { 'chunks': {}, 'last_index': None }
            file_transfers[key]['chunks'][chunk_index] = chunk_b64
            if last_flag == "1":
                file_transfers[key]['last_index'] = chunk_index
            # Verifica si se han recibido todos los _chunks_
            ft_entry = file_transfers[key]
            if ft_entry['last_index'] is not None:
                expected_chunks = ft_entry['last_index'] + 1
                if len(ft_entry['chunks']) == expected_chunks:
                    # Reensambla el archivo ordenando los _chunks_
                    chunks_ordered = [ft_entry['chunks'][i] for i in range(expected_chunks)]
                    file_data = b"".join(base64.b64decode(chunk) for chunk in chunks_ordered)
                    ruta_archivo = os.path.join(client_dir, filename)
                    with open(ruta_archivo, "wb") as f:
                        f.write(file_data)
                    log_message(f"Archivo {filename} recibido completo en {client_dir}")
                    del file_transfers[key]
        except Exception as ex:
            log_message(f"Error al procesar chunk de archivo: {ex}")

    # ----------------------------------------------------------------------
    # 9. Función para refrescar y mostrar los mensajes recibidos
    # ----------------------------------------------------------------------
    def refrescar_mensajes():
        while not mensajes_queue.empty():
            msg = mensajes_queue.get()
            if msg.startswith("FILE;"):
                process_file_chunk(msg)
            else:
                log_message(msg)
        page.update()

    # ----------------------------------------------------------------------
    # 10. Función para enviar un mensaje y enviar el archivo en _chunks_
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

        # Enviar primer mensaje de texto con el mensaje y nombre del archivo
        contenido = f"{usuario}: {mensaje}\narchivo: {os.path.basename(selected_file)}"
        datagrama = Midatagrama.crear_datagrama(server_ip, server_port, contenido)
        try:
            sock.sendto(datagrama.get_bytes(), (datagrama.ip, datagrama.puerto))
            log_message("Mensaje enviado")
            txt_mensaje.value = ""
        except Exception as ex:
            log_message(f"Error al enviar mensaje: {ex}")

        # Enviar el archivo en _chunks_
        chunk_size = 1024  # tamaño similar a byte[] buffer = new byte[1024]
        try:
            with open(selected_file, "rb") as f:
                chunk_index = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    # Codifica el chunk en base64 para enviarlo como texto
                    chunk_b64 = base64.b64encode(chunk).decode('utf-8')
                    # Si el chunk leído es menor que el tamaño esperado, es el último
                    last_flag = "1" if len(chunk) < chunk_size else "0"
                    # Construye el mensaje para el _chunk_
                    file_msg = f"FILE;{usuario};{os.path.basename(selected_file)};{chunk_index};{last_flag};{chunk_b64}"
                    datagrama_file = Midatagrama.crear_datagrama(server_ip, server_port, file_msg)
                    sock.sendto(datagrama_file.get_bytes(), (datagrama_file.ip, datagrama_file.puerto))
                    log_message(f"Enviado chunk {chunk_index} (last: {last_flag})")
                    chunk_index += 1
        except Exception as ex:
            log_message(f"Error al enviar archivo: {ex}")
        finally:
            page.update()

    btn_enviar = ft.ElevatedButton("Enviar", on_click=enviar_click)

    # ----------------------------------------------------------------------
    # 11. Botón "Refrescar" para leer mensajes pendientes
    # ----------------------------------------------------------------------
    def refrescar_click(e):
        refrescar_mensajes()

    btn_refrescar = ft.ElevatedButton("Refrescar", on_click=refrescar_click)

    # ----------------------------------------------------------------------
    # 12. Disposición de la interfaz
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
    # 13. Enviar mensaje de registro para que el servidor registre el cliente
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
    
    # Si se pasa un argumento se entiende que es una instancia secundaria
    if len(sys.argv) > 1:
        ft.app(target=Emisor)
    else:
        # Esta instancia "maestra" lanza las demás instancias
        for i in range(1, num_clients):
            username = config["CLIENT"].get("username").strip()
            subprocess.Popen(["python", "-m", "cliente.cliente", str(i+1)])
            print(f"Lanzando cliente {i+1} con username: {username}")
        ft.app(target=Emisor)
