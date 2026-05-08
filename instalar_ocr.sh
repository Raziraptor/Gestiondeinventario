#!/bin/bash
# Instala dependencias para OCR de recibos (Tesseract + pytesseract + pdf2image)
# Ejecutar en el servidor como root: bash instalar_ocr.sh

set -e
echo "==> Instalando Tesseract OCR + idioma español..."
apt-get update -qq
apt-get install -y tesseract-ocr tesseract-ocr-spa poppler-utils

echo "==> Instalando paquetes Python..."
source /root/venv/bin/activate
pip install pytesseract Pillow pdf2image

echo "==> Verificando instalación..."
tesseract --version
python -c "import pytesseract; print('pytesseract OK')"
python -c "from pdf2image import convert_from_bytes; print('pdf2image OK')"

echo ""
echo "✓ OCR listo. Reinicia el servicio: sudo systemctl restart inventario"
