#!/bin/bash
set -e

APP_NAME="korvex-antichatter"
VERSION="1.0.0"
MAINTAINER="Miki Colmena <macolmena60@gmail.com>"
DESCRIPTION="Filtro anti-rebotes de teclado"
PKG_DIR="build/deb/${APP_NAME}_${VERSION}_all"

# Limpiar build anterior
rm -rf build/deb
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/pixmaps"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/lib/python3/dist-packages"

# Copiar archivos
cp main.py "${PKG_DIR}/usr/bin/${APP_NAME}"
chmod 755 "${PKG_DIR}/usr/bin/${APP_NAME}"
cp KorvexLogo.png "${PKG_DIR}/usr/share/pixmaps/KorvexLogo.png"

# Instalar keyboard dentro del paquete
pip install --target="${PKG_DIR}/usr/lib/python3/dist-packages" keyboard

# Archivo control
cat > "${PKG_DIR}/DEBIAN/control" <<EOF
Package: ${APP_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: ${MAINTAINER}
Depends: python3, python3-pyqt6, pkexec
Description: ${DESCRIPTION}
EOF

# Script postinst
cat > "${PKG_DIR}/DEBIAN/postinst" <<EOF
#!/bin/sh
set -e
cat > /usr/share/applications/${APP_NAME}.desktop <<EOF2
[Desktop Entry]
Type=Application
Name=KORVEX Anti-Chatter
Comment=${DESCRIPTION}
Exec=/usr/bin/${APP_NAME}
Icon=KorvexLogo
Terminal=false
Categories=Utility;
EOF2
exit 0
EOF
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# Script postrm
cat > "${PKG_DIR}/DEBIAN/postrm" <<EOF
#!/bin/sh
set -e
rm -f /usr/share/applications/${APP_NAME}.desktop
exit 0
EOF
chmod 755 "${PKG_DIR}/DEBIAN/postrm"

# Construir .deb
dpkg-deb --build "${PKG_DIR}" "${APP_NAME}_${VERSION}_all.deb"
echo "Paquete creado: ${APP_NAME}_${VERSION}_all.deb"