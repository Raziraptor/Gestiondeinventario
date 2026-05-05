# Publicar en Google Play Store (TWA)

Una TWA (Trusted Web Activity) empaqueta la PWA como app Android nativa
sin escribir código Java/Kotlin. Usa Bubblewrap (CLI oficial de Google).

## Requisitos

- Node.js 16+
- Java JDK 11+ (para firmar el APK)
- Cuenta Google Play Developer ($25 única vez)

## Pasos

### 1. Instalar Bubblewrap

```bash
npm install -g @bubblewrap/cli
```

### 2. Generar el proyecto Android

```bash
mkdir gestor-inventario-android && cd gestor-inventario-android
bubblewrap init --manifest https://TU_DOMINIO/static/manifest.json
```

Bubblewrap preguntará datos durante la configuración. Usa estos valores:
- **Application ID**: com.tuempresa.inventario
- **Display mode**: standalone
- **Signing key**: crea una nueva (Bubblewrap la genera)

### 3. Obtener el SHA-256 del keystore

Después de `bubblewrap init`, obtén el fingerprint:

```bash
keytool -list -v -keystore android.keystore -alias android -storepass android
```

Copia el valor SHA256 (formato: `AA:BB:CC:...`).

### 4. Agregar assetlinks.json al servidor

Edita `app.py` y busca `ASSETLINKS`. Agrega tu configuración:

```python
app.config['ASSETLINKS'] = [
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.tuempresa.inventario",
      "sha256_cert_fingerprints": ["AA:BB:CC:...TU_FINGERPRINT..."]
    }
  }
]
```

Luego reinicia gunicorn. Verifica en:
`https://TU_DOMINIO/.well-known/assetlinks.json`

### 5. Compilar y subir

```bash
bubblewrap build
```

Genera `app-release-signed.apk`. Súbelo a Google Play Console
en **Producción** → **Versiones** → **Crear versión**.

## Verificar que funciona

Usa la herramienta oficial de Google para validar:
https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://TU_DOMINIO&relation=delegate_permission/common.handle_all_urls

## iOS / App Store

Para iOS se necesita un wrapper nativo (Capacitor o similar) y una cuenta
Apple Developer ($99/año). La instalación vía Safari ("Añadir a inicio")
ya funciona con la configuración actual, aunque sin prompt automático.
