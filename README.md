# 🛡️ KORVEX Anti-Chatter

Aplicación para eliminar el rebote de teclas (*chatter*) en teclados mecánicos.
Bloquea las pulsaciones dobles no deseadas antes de que lleguen a ninguna aplicación, en Windows y Linux.

![Plataformas](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)
![Licencia](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Características

- **Bloqueo real** de los rebotes: la pulsación repetida nunca llega al sistema (no se escribe y luego se borra).
- Umbrales configurables para las teclas y, por separado, para la barra espaciadora.
- **Filtrar todas las teclas** (excepto Shift, Ctrl, Alt y Win/Super) o **solo las que elijas**, con un contador de rebotes por tecla para saber cuáles fallan.
- No filtra las pulsaciones generadas por software (autoescritura de gestores de contraseñas, macros…).
- Funciona en **X11 y Wayland** sin ejecutarse como root.
- Bandeja del sistema con pausa/reanudación, inicio automático y arranque oculto.
- Interfaz en español e inglés (según el idioma del sistema).

---

## 📥 Descarga e instalación

### Windows

1. Descarga `KorvexAntiChatter-windows.zip` desde [Releases](https://github.com/mikicolmena/KORVEX-Anti-Chatter/releases/latest).
2. Descomprímelo donde quieras (por ejemplo, en `Documentos`) y ejecuta `KorvexAntiChatter.exe` desde la carpeta.
3. Si aparece SmartScreen, pulsa «Más información» → «Ejecutar de todas formas».

> **Antivirus:** el programa no está firmado digitalmente y, como intercepta el teclado para filtrarlo, algunos
> antivirus pueden marcarlo como sospechoso (falso positivo). No envía nada a ninguna parte ni guarda lo que escribes;
> el código fuente completo está en este repositorio.

> Windows no deja que un programa normal intercepte el teclado en ventanas que se ejecutan como administrador.
> Si necesitas el filtro también en esas ventanas, ejecuta KORVEX como administrador.

### Linux (Debian 12+ / Ubuntu 22.04+)

#### Opción A: repositorio APT (recomendado, con actualizaciones automáticas)

```bash
# Clave pública del repositorio
wget -O- https://mikicolmena.github.io/KORVEX-Anti-Chatter/public.key | sudo gpg --dearmor -o /usr/share/keyrings/korvex.gpg

# Repositorio
echo "deb [signed-by=/usr/share/keyrings/korvex.gpg] https://mikicolmena.github.io/KORVEX-Anti-Chatter stable main" | sudo tee /etc/apt/sources.list.d/korvex.list

# Instalar
sudo apt update
sudo apt install korvex-antichatter
```

Las actualizaciones llegarán con `sudo apt update && sudo apt upgrade`.

#### Opción B: paquete .deb suelto

Descarga `korvex-antichatter_<versión>_all.deb` desde [Releases](https://github.com/mikicolmena/KORVEX-Anti-Chatter/releases/latest) e instálalo:

```bash
sudo apt install ./korvex-antichatter_*_all.deb
```

Con este método no recibirás actualizaciones automáticas.

#### Permisos en Linux

El paquete instala una regla udev que da acceso a los teclados y a `/dev/uinput` **al usuario de la sesión local activa**,
así que el programa funciona sin contraseña ni root. Si justo después de instalar indica que no tiene permisos,
cierra sesión y vuelve a entrar. La propia aplicación muestra los pasos alternativos (grupo `input`) si hicieran falta.

> Ten en cuenta que, igual que cualquier herramienta de este tipo, esto permite a los programas de tu sesión leer el teclado.
> Si otro usuario inicia sesión en el mismo equipo (cambio rápido de usuario), KORVEX suelta el teclado automáticamente.

#### Icono en la bandeja (GNOME)

GNOME no muestra iconos de bandeja de serie. Ubuntu ya trae la extensión necesaria; en Debian, Fedora y otros instala
**AppIndicator and KStatusNotifierItem Support** (`sudo apt install gnome-shell-extension-appindicator` en Debian).
Sin bandeja, «Minimizar» deja la ventana minimizada en la barra de tareas.

---

## ⚙️ Cómo funciona

Cuando un interruptor rebota, el sistema recibe *soltar → pulsar* de la misma tecla en muy pocos milisegundos.
KORVEX mide el tiempo entre que una tecla se suelta y se vuelve a pulsar: si es menor que el umbral, esa pulsación
(y su liberación) se descartan.

- **Windows:** hook de teclado de bajo nivel (`WH_KEYBOARD_LL`).
- **Linux:** captura exclusiva del teclado físico con evdev y reenvío de las pulsaciones válidas por un teclado virtual (uinput).

**Consejo:** si escribes muy rápido y alguna letra doble legítima («ll», «rr», «cc») desaparece, baja el umbral o usa
el modo «Solo las seleccionadas» con las teclas que realmente fallan (la ventana «Elegir teclas…» muestra cuántos rebotes ha tenido cada una).

---

## 🩺 Registro de diagnóstico

Si algo falla, el programa guarda un registro pequeño (nunca guarda qué teclas pulsas):

- **Linux:** `~/.local/state/korvex-antichatter/korvex.log`
- **Windows:** `%LOCALAPPDATA%\KorvexAntiChatter\korvex.log`

Adjúntalo si abres una incidencia.

---

## 🧑‍💻 Ejecutar desde el código fuente

```bash
# Linux
sudo apt install python3-pyqt6 python3-evdev
python3 main.py

# Windows
pip install PyQt6
python main.py
```

En Linux, sin el paquete instalado, necesitarás los permisos descritos arriba (la app te indica cómo).

### Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

Se ejecutan automáticamente en GitHub Actions con cada push y antes de cada publicación.

### Publicar una versión

Crea una release en GitHub con un tag que contenga el número de versión (`Version1.2`, `v1.2.0`…).
El workflow pasa los tests, construye el `.deb` y el `.zip` de Windows con esa versión, los adjunta a la release
y actualiza el repositorio APT firmado en GitHub Pages.

**Firma del ejecutable de Windows (opcional):** si añades en *Settings → Secrets and variables → Actions* los secretos
`WINDOWS_CERT_PFX_BASE64` (tu certificado de firma de código `.pfx` en base64) y `WINDOWS_CERT_PASSWORD`, el workflow
firma `KorvexAntiChatter.exe` automáticamente. Sin ellos, se publica sin firmar.

---

## 📄 Licencia

[MIT](LICENSE)
