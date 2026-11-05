"""Traducciones sencillas (español / inglés) según el idioma del sistema."""

import locale
import os

_STRINGS = {
    "es": {
        "threshold_letters": "Umbral teclas:",
        "threshold_space": "Umbral espacio:",
        "filter_mode": "Teclas a filtrar:",
        "mode_all": "Todas (sin modificadores)",
        "mode_selected": "Solo las seleccionadas",
        "configure_keys": "Elegir teclas…",
        "close_action": "Al cerrar la ventana:",
        "close_ask": "Preguntar",
        "close_minimize": "Minimizar a la bandeja",
        "close_exit": "Salir del programa",
        "autostart": "Iniciar automáticamente con el sistema",
        "start_minimized": "Arrancar escondido en la bandeja",
        "btn_active": "FILTRO ACTIVO (PAUSAR)",
        "btn_paused": "FILTRO PAUSADO (INICIAR)",
        "stats": "Rebotes evitados: {total}",
        "stats_last": "Último bloqueo: '{key}' | Rebotes evitados: {total}",
        "reset_stats": "Reiniciar contador",
        "tray_show": "Mostrar interfaz",
        "tray_pause": "Pausar filtro",
        "tray_resume": "Reanudar filtro",
        "tray_quit": "Cerrar del todo",
        "tray_bg_title": "Sigue funcionando",
        "tray_bg_msg": "El filtro sigue activo en segundo plano. Haz clic en el icono para abrir la ventana.",
        "close_q_title": "¿Qué deseas hacer?",
        "close_q_desc": "La protección del teclado se detendrá si cierras el programa.",
        "close_q_remember": "Recordar mi elección y no volver a preguntar",
        "cancel": "Cancelar",
        "keys_title": "Teclas a filtrar",
        "keys_help": "Marca las teclas que rebotan. Solo se usan con el modo «Solo las seleccionadas».\nEl número indica cuántos rebotes se han detectado en cada tecla.",
        "keys_add": "Añadir tecla…",
        "keys_remove": "Quitar",
        "keys_bounces": "{name}  —  rebotes: {count}",
        "capture_title": "Añadir tecla",
        "capture_msg": "Pulsa la tecla que quieres añadir…",
        "ok": "Aceptar",
        "err_title": "No se pudo iniciar el filtro",
        "no_tray": "No hay bandeja del sistema disponible; la ventana permanecerá abierta.",
        "err_linux_perm": (
            "No hay permiso para acceder al teclado ({detail}).\n\n"
            "Si has instalado el paquete .deb, cierra sesión y vuelve a entrar.\n"
            "Si sigue fallando (o lo ejecutas desde el código fuente), añade tu usuario al grupo 'input' "
            "y permite el acceso a /dev/uinput:\n\n"
            "  sudo usermod -aG input $USER\n"
            "  echo 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\"' | sudo tee /etc/udev/rules.d/70-korvex-uinput.rules\n"
            "  sudo modprobe uinput && sudo udevadm trigger\n\n"
            "y después cierra sesión y vuelve a entrar."
        ),
        "err_no_uinput": "No existe /dev/uinput. Carga el módulo con: sudo modprobe uinput",
        "err_no_keyboard": "No se ha encontrado ningún teclado.",
        "err_missing_evdev": "Falta la librería python3-evdev. Instálala con: sudo apt install python3-evdev",
        "err_unsupported": "Este sistema operativo no está soportado.",
        "err_hook": "No se pudo instalar el hook de teclado (código {code}).",
    },
    "en": {
        "threshold_letters": "Key threshold:",
        "threshold_space": "Space threshold:",
        "filter_mode": "Keys to filter:",
        "mode_all": "All (except modifiers)",
        "mode_selected": "Selected only",
        "configure_keys": "Choose keys…",
        "close_action": "When closing the window:",
        "close_ask": "Ask",
        "close_minimize": "Minimize to tray",
        "close_exit": "Quit the program",
        "autostart": "Start automatically with the system",
        "start_minimized": "Start hidden in the tray",
        "btn_active": "FILTER ON (PAUSE)",
        "btn_paused": "FILTER PAUSED (START)",
        "stats": "Bounces blocked: {total}",
        "stats_last": "Last blocked: '{key}' | Bounces blocked: {total}",
        "reset_stats": "Reset counter",
        "tray_show": "Show window",
        "tray_pause": "Pause filter",
        "tray_resume": "Resume filter",
        "tray_quit": "Quit",
        "tray_bg_title": "Still running",
        "tray_bg_msg": "The filter keeps running in the background. Click the icon to open the window.",
        "close_q_title": "What do you want to do?",
        "close_q_desc": "Keyboard protection will stop if you quit the program.",
        "close_q_remember": "Remember my choice and don't ask again",
        "cancel": "Cancel",
        "keys_title": "Keys to filter",
        "keys_help": "Tick the keys that chatter. Only used in \"Selected only\" mode.\nThe number shows how many bounces were detected on each key.",
        "keys_add": "Add key…",
        "keys_remove": "Remove",
        "keys_bounces": "{name}  —  bounces: {count}",
        "capture_title": "Add key",
        "capture_msg": "Press the key you want to add…",
        "ok": "OK",
        "err_title": "Could not start the filter",
        "no_tray": "No system tray available; the window will stay open.",
        "err_linux_perm": (
            "No permission to access the keyboard ({detail}).\n\n"
            "If you installed the .deb package, log out and log back in.\n"
            "If it still fails (or you run it from source), add your user to the 'input' group "
            "and allow access to /dev/uinput:\n\n"
            "  sudo usermod -aG input $USER\n"
            "  echo 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\"' | sudo tee /etc/udev/rules.d/70-korvex-uinput.rules\n"
            "  sudo modprobe uinput && sudo udevadm trigger\n\n"
            "then log out and log back in."
        ),
        "err_no_uinput": "/dev/uinput does not exist. Load the module with: sudo modprobe uinput",
        "err_no_keyboard": "No keyboard was found.",
        "err_missing_evdev": "The python3-evdev library is missing. Install it with: sudo apt install python3-evdev",
        "err_unsupported": "This operating system is not supported.",
        "err_hook": "Could not install the keyboard hook (code {code}).",
    },
}


def _detect_language():
    forced = os.environ.get("KORVEX_LANG")
    if forced in _STRINGS:
        return forced
    candidates = [os.environ.get(v) for v in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")]
    try:
        candidates.append(locale.getlocale()[0])
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            candidates.insert(0, "es" if (lang_id & 0x3FF) == 0x0A else "en")
        except Exception:
            pass
    for value in candidates:
        if value and value.lower().startswith("es"):
            return "es"
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return "en"
    return "es"


LANG = _detect_language()


def tr(msg_id, **kwargs):
    text = _STRINGS[LANG].get(msg_id) or _STRINGS["es"].get(msg_id, msg_id)
    return text.format(**kwargs) if kwargs else text
