# dto/Midatagrama.py

class Midatagrama:
    """
    DTO que encapsula la información de un datagrama UDP:
    - ip: Dirección IP del destinatario.
    - puerto: Puerto del destinatario.
    - mensaje: Contenido del mensaje en forma de cadena.
    """
    def __init__(self, ip: str, puerto: int, mensaje: str):
        self.ip = ip
        self.puerto = puerto
        self.mensaje = mensaje

    def get_bytes(self) -> bytes:
        """
        Retorna el mensaje codificado en bytes (UTF-8) para poder enviarlo mediante UDP.
        """
        return self.mensaje.encode('utf-8')

    @staticmethod
    def crear_datagrama(ip: str, puerto: int, mensaje: str) -> "Midatagrama":
        """
        Método estático que crea y retorna una instancia de Midatagrama.
        Permite separar la lógica de creación del objeto DTO.
        """
        return Midatagrama(ip, puerto, mensaje)
