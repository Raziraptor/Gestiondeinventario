#!/bin/bash
# Descarga fuentes Google Fonts (Apache/OFL) para generación de etiquetas PIL
# Ejecutar en el servidor: bash instalar_fuentes_etiqueta.sh

set -e
FONTS_DIR="/root/Gestiondeinventario/static/fonts"
BASE="https://github.com/google/fonts/raw/main"

mkdir -p "$FONTS_DIR"

echo "==> Descargando Inter..."
wget -q -O "$FONTS_DIR/Inter-Regular.ttf" "$BASE/ofl/inter/static/Inter-Regular.ttf"
wget -q -O "$FONTS_DIR/Inter-Bold.ttf"    "$BASE/ofl/inter/static/Inter-Bold.ttf"

echo "==> Descargando Roboto..."
wget -q -O "$FONTS_DIR/Roboto-Regular.ttf" "$BASE/apache/roboto/static/Roboto-Regular.ttf"
wget -q -O "$FONTS_DIR/Roboto-Bold.ttf"    "$BASE/apache/roboto/static/Roboto-Bold.ttf"

echo "==> Descargando Montserrat..."
wget -q -O "$FONTS_DIR/Montserrat-Regular.ttf" "$BASE/ofl/montserrat/static/Montserrat-Regular.ttf"
wget -q -O "$FONTS_DIR/Montserrat-Bold.ttf"    "$BASE/ofl/montserrat/static/Montserrat-Bold.ttf"

echo "==> Descargando Poppins..."
wget -q -O "$FONTS_DIR/Poppins-Regular.ttf" "$BASE/ofl/poppins/Poppins-Regular.ttf"
wget -q -O "$FONTS_DIR/Poppins-Bold.ttf"    "$BASE/ofl/poppins/Poppins-Bold.ttf"

echo "==> Descargando Oswald..."
wget -q -O "$FONTS_DIR/Oswald-Regular.ttf" "$BASE/ofl/oswald/static/Oswald-Regular.ttf"
wget -q -O "$FONTS_DIR/Oswald-Bold.ttf"    "$BASE/ofl/oswald/static/Oswald-Bold.ttf"

echo ""
echo "✓ Fuentes instaladas:"
ls -lh "$FONTS_DIR"/*.ttf
echo ""
echo "Reinicia el servicio: sudo systemctl restart inventario"
