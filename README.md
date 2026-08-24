# 🛡️ KORVEX Anti-Chatter

Aplicación para eliminar el rebote de teclas (chatter) en teclados mecánicos.  
Filtra de forma inteligente las pulsaciones dobles no deseadas en Windows y Linux.

![Versión](https://img.shields.io/badge/version-1.0.0-blue)
![Plataformas](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)
![Licencia](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Características

- Filtrado de rebotes con umbrales configurables para letras y espacio.
- Interfaz gráfica moderna con PyQt6.
- Modo bandeja del sistema.
- Inicio automático con el sistema.
- Estadísticas de rebotes bloqueados.
- Disponible para **Windows** y **Linux (Debian/Ubuntu)**.

---

## 📥 Descarga e instalación

### Windows

1. Descarga `KorvexAntiChatter.exe` desde la sección [Releases](https://github.com/mikicolmena/KORVEX-Anti-Chatter/releases).
2. Ejecuta el archivo descargado.
3. Si aparece SmartScreen, pulsa "Más información" y "Ejecutar de todas formas".

### Linux (Debian/Ubuntu)

#### Opción A: Añadir repositorio APT (recomendado)

Con este método instalas la aplicación y recibes actualizaciones automáticas con `apt upgrade`.  
Copia y pega estos comandos en una terminal:

```bash
# Añadir clave pública del repositorio
wget -O- https://mikicolmena.github.io/KORVEX-Anti-Chatter/public.key | sudo gpg --dearmor -o /usr/share/keyrings/korvex.gpg

# Añadir el repositorio
echo "deb [signed-by=/usr/share/keyrings/korvex.gpg] https://mikicolmena.github.io/KORVEX-Anti-Chatter stable main" | sudo tee /etc/apt/sources.list.d/korvex.list

# Actualizar e instalar
sudo apt update
sudo apt install korvex-antichatter