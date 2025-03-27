# servidor/servidor.py

import flet as ft
import socket
import threading
import queue
import configparser

def Receptor(page: ft.Page):
    """
    Servidor UDP con Flet que:
    - Lee la configuración desde config.ini
    - Escucha en el puerto indicado
    - Reenvía los mensajes a todos los clientes conectados excepto al remitente
    - Muestra mensajes en la interfaz
    """
    page.title = "Servidor UDP - Receptor"
    
    # Centrado vertical y horizontal de todo el contenido
    page.horizontal_alignment = "center"
    page.vertical_alignment = "center"
    
    # -------------------------------------------------------------------------
    # 1. Lectura de config.ini
    # -------------------------------------------------------------------------
    config = configparser.ConfigParser()
    config.read(r"C:\Users\Usuario\desktop\app_udp_python\config.ini")
    print("Secciones encontradas en config.ini:", config.sections())

    # Tomamos el puerto del servidor desde la sección [SERVER]
    server_port = int(config["SERVER"]["port"])
    max_clients = int(config["SERVER"].get("max_clients", "10"))
    
    # Etiqueta de título
    lbl_titulo = ft.Text(
        "SERVIDOR UDP",
        color="blue",
        weight="bold",
        size=20
    )

    # Área de texto donde se muestran los mensajes
    txt_mensajes = ft.TextField(
        value="",
        multiline=True,
        width=450,
        height=250,
        read_only=True
    )
    
    # Cola para almacenar mensajes recibidos en el hilo secundario
    mensajes_queue = queue.Queue()

    # Conjunto de direcciones (ip, puerto) de clientes conectados
    connected_clients = set()

    # Hilo de escucha (se define al pulsar el botón "Iniciar Servidor")
    hilo_escucha = None

    def escuchar_udp():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", server_port))
        
        print(f"Servidor UDP iniciado en el puerto {server_port}")
        mensajes_queue.put(("INFO", f"Servidor UDP iniciado en el puerto {server_port}\nEscuchando...\n"))

        while True:
            try:
                # Se utiliza un buffer mayor para recibir mensajes grandes
                data, addr = sock.recvfrom(65535)
                mensaje = data.decode('utf-8')
                
                # Registrar al cliente si aún no está en la lista
                if addr not in connected_clients:
                    connected_clients.add(addr)

                # Guardar el mensaje para mostrarlo en la interfaz
                mensajes_queue.put((addr, mensaje))

                # Reenviar el mensaje solo a los demás clientes
                if "se ha conectado" not in mensaje:
                    for client_addr in list(connected_clients):
                        if client_addr != addr:
                            try:
                                sock.sendto(data, client_addr)
                            except OSError as e:
                                print(f"No se pudo enviar a {client_addr}: {e}")
                                connected_clients.remove(client_addr)

            except Exception as e:
                print("Error al recibir mensaje:", e)
                mensajes_queue.put(("INFO", f"Error al recibir mensaje: {e}\n"))
                break

    def iniciar_servidor_click(e):
        """
        Función que se ejecuta al pulsar "Iniciar Servidor".
        Crea e inicia el hilo de escucha y deshabilita el botón.
        """
        nonlocal hilo_escucha
        if hilo_escucha is None:
            hilo_escucha = threading.Thread(target=escuchar_udp, daemon=True)
            hilo_escucha.start()
            btn_iniciar.disabled = True
            page.update()

    def refrescar_click(e):
        """
        Función que se ejecuta al pulsar "Refrescar".
        Lee todos los mensajes de la cola y los muestra en 'txt_mensajes',
        filtrando los mensajes de chunks (que comienzan con "FILE;") para no saturar la UI.
        """
        while not mensajes_queue.empty():
            addr, mensaje = mensajes_queue.get()
            if addr == "INFO":
                txt_mensajes.value += mensaje
            else:
                # Si el mensaje es de un chunk, lo ignoramos en la interfaz
                if mensaje.startswith("FILE;"):
                    # Opcional: imprimir detalles en la consola (truncado)
                    print(f"Chunk recibido de {addr}: {mensaje[:50]}...")
                else:
                    txt_mensajes.value += (
                        f"Remitente {addr}\n"
                        "El mensaje recibido es:\n"
                        f"{mensaje}\n"
                        "Escuchando...\n"
                    )
        page.update()

    # Botón para iniciar el servidor
    btn_iniciar = ft.ElevatedButton("Iniciar Servidor", on_click=iniciar_servidor_click)
    
    # Botón para refrescar los mensajes pendientes
    btn_refrescar = ft.ElevatedButton("Refrescar", on_click=refrescar_click)

    # Organizar la interfaz en una columna centrada
    layout = ft.Column(
        controls=[
            lbl_titulo,
            txt_mensajes,
            ft.Row([btn_iniciar, btn_refrescar], alignment="center")
        ],
        alignment="center",
        horizontal_alignment="center"
    )

    page.add(layout)

# Iniciar la aplicación Flet
if __name__ == "__main__":
    ft.app(target=Receptor)
