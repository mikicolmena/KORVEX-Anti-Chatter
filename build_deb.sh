#!/bin/bash
# Construye el paquete .deb de KORVEX Anti-Chatter en dist/.
#
# Uso:  ./build_deb.sh            -> versión de korvex/__init__.py
#       VERSION=Version1.2 ./build_deb.sh  (el workflow pasa el tag de la release)
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="korvex-antichatter"
DESKTOP_ID="io.github.mikicolmena.KorvexAntiChatter"
MAINTAINER="Miki Colmena <macolmena60@gmail.com>"

if [ -z "${VERSION:-}" ]; then
    VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' korvex/__init__.py)"
fi
VERSION="$(python3 packaging/set_version.py --print "$VERSION")"   # admite "Version1.2", "v1.2.0"…
if ! [[ "$VERSION" =~ ^[0-9][A-Za-z0-9.+~-]*$ ]]; then
    echo "Versión no válida para Debian: '$VERSION'" >&2
    exit 1
fi

BUILD="build/deb"
PKG="${BUILD}/${APP_NAME}_${VERSION}_all"
SHARE="${PKG}/usr/share/${APP_NAME}"
OUT="dist/${APP_NAME}_${VERSION}_all.deb"

rm -rf "$BUILD"
mkdir -p "${PKG}/DEBIAN" "${PKG}/usr/bin" "$SHARE" \
         "${PKG}/usr/share/applications" \
         "${PKG}/usr/share/icons/hicolor/256x256/apps" \
         "${PKG}/usr/lib/udev/rules.d" \
         "${PKG}/usr/lib/modules-load.d" \
         "${PKG}/usr/share/doc/${APP_NAME}" \
         dist

# Código de la aplicación (sin cachés de Python)
cp main.py "$SHARE/"
cp -r korvex "$SHARE/"
find "$SHARE" -name "__pycache__" -type d -prune -exec rm -rf {} +
sed -i "s/^__version__ = .*/__version__ = \"${VERSION}\"/" "$SHARE/korvex/__init__.py"

# Integración con el sistema
install -m 755 packaging/linux/korvex-antichatter "${PKG}/usr/bin/${APP_NAME}"
install -m 644 "packaging/linux/${DESKTOP_ID}.desktop" "${PKG}/usr/share/applications/"
install -m 644 korvex/assets/korvex-antichatter.png "${PKG}/usr/share/icons/hicolor/256x256/apps/"
install -m 644 packaging/linux/70-korvex-antichatter.rules "${PKG}/usr/lib/udev/rules.d/"
install -m 644 packaging/linux/modules-load-korvex-antichatter.conf "${PKG}/usr/lib/modules-load.d/${APP_NAME}.conf"
install -m 644 LICENSE "${PKG}/usr/share/doc/${APP_NAME}/copyright"
install -m 755 packaging/debian/postinst packaging/debian/postrm "${PKG}/DEBIAN/"

find "$PKG" -type d -exec chmod 755 {} +
find "$SHARE" -type f -exec chmod 644 {} +

INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)"
cat > "${PKG}/DEBIAN/control" <<EOF
Package: ${APP_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ${MAINTAINER}
Installed-Size: ${INSTALLED_SIZE}
Depends: python3 (>= 3.8), python3-pyqt6, python3-evdev
Homepage: https://github.com/mikicolmena/KORVEX-Anti-Chatter
Description: Filtro anti-rebotes (chatter) para teclados mecánicos
 Bloquea las pulsaciones dobles no deseadas que producen los interruptores
 mecánicos desgastados. Funciona en X11 y Wayland, con umbrales
 configurables y la opción de filtrar solo las teclas que fallan.
EOF

dpkg-deb --root-owner-group --build "$PKG" "$OUT"
echo "Paquete creado: $OUT"
