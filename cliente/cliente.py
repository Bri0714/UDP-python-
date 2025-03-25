# cliente/cliente.py

import flet as ft
import socket
import threading
import queue
from dto.Midatagrama import Midatagrama
import configparser
import sys
import subprocess

def main(page: ft.Page):
    page.title = "Cliente UDP - Emisor y Receptor"
    
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

    # ----------------------------------------------------------------------
    # 2. Componentes de la UI
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

    txt_estado = ft.TextField(
        value="",
        multiline=True,
        width=250,
        height=150,
        read_only=True
    )

    btn_enviar = ft.ElevatedButton("Enviar")

    # ----------------------------------------------------------------------
    # 3. Crear socket para envío y recepción
    # ----------------------------------------------------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Bind en un puerto aleatorio para recibir respuestas
    sock.bind(("0.0.0.0", 0))

    # Cola para los mensajes recibidos en el hilo
    mensajes_queue = queue.Queue()

    # ----------------------------------------------------------------------
    # 4. Hilo de recepción
    # ----------------------------------------------------------------------
    def escuchar():
        """
        Hilo que permanece escuchando en el socket local.
        Cada datagrama se decodifica y se coloca en mensajes_queue.
        """
        while True:
            try:
                data, addr = sock.recvfrom(1024)
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
    # 5. Función para refrescar mensajes en la interfaz
    # ----------------------------------------------------------------------
    def refrescar_mensajes():
        """
        Saca todos los mensajes de la cola mensajes_queue y los concatena en txt_estado.
        """
        while not mensajes_queue.empty():
            msg = mensajes_queue.get()
            txt_estado.value += f"{msg}\n"

    # ----------------------------------------------------------------------
    # 6. Función para enviar un mensaje
    # ----------------------------------------------------------------------
    def enviar_click(e):
        usuario = txt_usuario.value.strip()
        mensaje = txt_mensaje.value.strip()

        # Validación: ambos campos vacíos
        if not usuario and not mensaje:
            txt_estado.value += "Debe ingresar un usuario y un mensaje\n"
            page.update()
            return

        # Validación: campo usuario vacío
        if not usuario:
            txt_estado.value += "No has ingresado usuario, por favor intenta enviar nuevamente\n"
            page.update()
            return

        # Validación: campo mensaje vacío
        if not mensaje:
            txt_estado.value += "No hay mensaje para enviar\n"
            page.update()
            return

        contenido = f"{usuario}: {mensaje}"
        datagrama = Midatagrama.crear_datagrama(server_ip, server_port, contenido)

        try:
            sock.sendto(datagrama.get_bytes(), (datagrama.ip, datagrama.puerto))
            txt_estado.value += "Mensaje enviado\n"
            txt_mensaje.value = ""
        except Exception as ex:
            txt_estado.value += f"Error al enviar: {ex}\n"
        finally:
            page.update()

    btn_enviar.on_click = enviar_click

    # ----------------------------------------------------------------------
    # 7. Botón "Refrescar" para actualizar la interfaz con mensajes pendientes
    # ----------------------------------------------------------------------
    def refrescar_click(e):
        refrescar_mensajes()
        page.update()

    btn_refrescar = ft.ElevatedButton("Refrescar", on_click=refrescar_click)

    # ----------------------------------------------------------------------
    # 8. Disposición de la interfaz
    # ----------------------------------------------------------------------
    layout = ft.Column(
        controls=[
            lbl_titulo,
            lbl_usuario,
            txt_usuario,
            lbl_mensaje,
            txt_mensaje,
            ft.Row([btn_enviar, btn_refrescar], alignment="center"),
            txt_estado
        ],
        alignment="center",
        horizontal_alignment="center"
    )

    page.add(layout)

    # ----------------------------------------------------------------------
    # 9. Enviar mensaje de registro para que el servidor registre el cliente
    # ----------------------------------------------------------------------
    # Se envía el mensaje usando el valor ingresado en el campo de usuario.
    registro = f"{txt_usuario.value.strip()} se ha conectado"
    datagrama_registro = Midatagrama.crear_datagrama(server_ip, server_port, registro)
    try:
        sock.sendto(datagrama_registro.get_bytes(), (datagrama_registro.ip, datagrama_registro.puerto))
        txt_estado.value += "Registrado en el servidor\n"
        page.update()
    except Exception as ex:
        txt_estado.value += f"Error al registrar: {ex}\n"
        page.update()


# ----------------------------------------------------------------------
# Lanzamiento automático de N clientes (desde el mismo cliente)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read("config.ini")
    num_clients = int(config["APP"].get("num_clients", "1"))
    
    # Si se pasa un argumento, se entiende que es una instancia secundaria
    if len(sys.argv) > 1:
        ft.app(target=main)
    else:
        # Esta instancia "maestra" lanza las demás instancias
        for i in range(1, num_clients):
            username = config["CLIENT"].get("username").strip()
            subprocess.Popen(["python", "-m", "cliente.cliente", username])
            print(f"Lanzando cliente {i+1} con username: {username}")
        ft.app(target=main)