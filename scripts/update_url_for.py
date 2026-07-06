"""
Script idempotente para actualizar url_for() en templates y Python files.
Convierte endpoints del monolito a los nuevos nombres de Blueprint.

Uso: python scripts/update_url_for.py [--dry-run]
"""

import re
import sys
import os
import glob

# Mapa completo: endpoint_viejo → blueprint.endpoint_nuevo
ENDPOINT_MAP = {
    # auth
    'login':            'auth.login',
    'logout':           'auth.logout',
    'register':         'auth.register',
    'forgot_password':  'auth.forgot_password',
    'reset_password':   'auth.reset_password',
    'account':          'auth.account',
    'delete_picture':   'auth.delete_picture',

    # main
    'index':                  'main.index',
    'dashboard':              'main.dashboard',
    'offline_page':           'main.offline_page',
    'service_worker':         'main.service_worker',
    'assetlinks':             'main.assetlinks',
    'historial_actividad':    'main.historial_actividad',

    # admin
    'lista_usuarios':         'admin.lista_usuarios',
    'admin_reset_password':   'admin.admin_reset_password',
    'super_admin':            'admin.super_admin',
    'nueva_organizacion':     'admin.nueva_organizacion',
    'asignar_usuario':        'admin.asignar_usuario',
    'admin_panel':            'admin.admin_panel',
    'configurar_plantilla':   'admin.configurar_plantilla',
    'historial_actividad':    'admin.historial_actividad',

    # inventory
    'lista_productos_sin_almacen':     'inventory.lista_productos_sin_almacen',
    'nuevo_producto':                  'inventory.nuevo_producto',
    'editar_producto':                 'inventory.editar_producto',
    'historial_producto':              'inventory.historial_producto',
    'generar_etiqueta':                'inventory.generar_etiqueta',
    'configurar_etiqueta':             'inventory.configurar_etiqueta',
    'generar_etiqueta_personalizada':  'inventory.generar_etiqueta_personalizada',
    'configurar_etiqueta_diseno':      'inventory.configurar_etiqueta_diseno',
    'configurar_excel_diseno':         'inventory.configurar_excel_diseno',
    'lista_categorias':                'inventory.lista_categorias',
    'nueva_categoria':                 'inventory.nueva_categoria',
    'editar_categoria':                'inventory.editar_categoria',
    'eliminar_categoria':              'inventory.eliminar_categoria',
    'lista_almacenes':                 'inventory.lista_almacenes',
    'nuevo_almacen':                   'inventory.nuevo_almacen',
    'editar_almacen':                  'inventory.editar_almacen',
    'eliminar_almacen':                'inventory.eliminar_almacen',
    'gestionar_inventario_almacen':    'inventory.gestionar_inventario_almacen',
    'eliminar_producto_de_almacen':    'inventory.eliminar_producto_de_almacen',
    'asignar_producto_rapido':         'inventory.asignar_producto_rapido',
    'historial_salidas':               'inventory.historial_salidas',
    'ver_salida':                      'inventory.ver_salida',
    'registrar_salida':                'inventory.registrar_salida',
    'eliminar_movimiento_salida':      'inventory.eliminar_movimiento_salida',
    'generar_salida_pdf':              'inventory.generar_salida_pdf',
    'importar_productos':              'inventory.importar_productos',
    'descargar_template_importacion':  'inventory.descargar_template_importacion',
    'nueva_transferencia':             'inventory.nueva_transferencia',
    'nuevo_ajuste':                    'inventory.nuevo_ajuste',

    # purchasing
    'lista_proveedores':          'purchasing.lista_proveedores',
    'nuevo_proveedor':            'purchasing.nuevo_proveedor',
    'editar_proveedor':           'purchasing.editar_proveedor',
    'guardar_integracion_hd':     'purchasing.guardar_integracion_hd',
    'lista_ordenes':              'purchasing.lista_ordenes',
    'nueva_orden':                'purchasing.nueva_orden',
    'recibir_orden':              'purchasing.recibir_orden',
    'enviar_orden':               'purchasing.enviar_orden',
    'generar_oc_pdf':             'purchasing.generar_oc_pdf',
    'nueva_orden_manual':         'purchasing.nueva_orden_manual',
    'ver_orden':                  'purchasing.ver_orden',
    'exportar_hd_csv':            'purchasing.exportar_hd_csv',
    'exportar_proyecto_hd_csv':   'purchasing.exportar_proyecto_hd_csv',
    'subir_hd_auto':              'purchasing.subir_hd_auto',
    'editar_orden':               'purchasing.editar_orden',
    'cancelar_orden':             'purchasing.cancelar_orden',
    'eliminar_orden':             'purchasing.eliminar_orden',
    'lista_proyectos_oc':         'purchasing.lista_proyectos_oc',
    'ver_proyecto_oc':            'purchasing.ver_proyecto_oc',
    'nuevo_proyecto_oc':          'purchasing.nuevo_proyecto_oc',
    'editar_proyecto_oc':         'purchasing.editar_proyecto_oc',
    'solicitar_aprobacion_oc':    'purchasing.solicitar_aprobacion_oc',
    'enviar_proyecto_oc':         'purchasing.enviar_proyecto_oc',
    'lista_aprobaciones':         'purchasing.lista_aprobaciones',
    'aprobar_solicitud':          'purchasing.aprobar_solicitud',
    'rechazar_solicitud':         'purchasing.rechazar_solicitud',
    'recibir_proyecto_oc':        'purchasing.recibir_proyecto_oc',
    'generar_proyecto_oc_pdf':    'purchasing.generar_proyecto_oc_pdf',
    'cancelar_proyecto_oc':       'purchasing.cancelar_proyecto_oc',
    'exportar_proyectos_oc_excel':'purchasing.exportar_proyectos_oc_excel',

    # finance
    'finanzas_dashboard':     'finance.finanzas_dashboard',
    'lista_gastos':           'finance.lista_gastos',
    'nuevo_gasto':            'finance.nuevo_gasto',
    'editar_gasto':           'finance.editar_gasto',
    'exportar_gastos_excel':  'finance.exportar_gastos_excel',
    'lista_centros_costo':    'finance.lista_centros_costo',
    'nuevo_centro_costo':     'finance.nuevo_centro_costo',
    'editar_centro_costo':    'finance.editar_centro_costo',
    'cerrar_centro_costo':    'finance.cerrar_centro_costo',
    'detalle_centro_costo':   'finance.detalle_centro_costo',
    'lista_presupuestos':     'finance.lista_presupuestos',
    'nuevo_presupuesto':      'finance.nuevo_presupuesto',
    'editar_presupuesto':     'finance.editar_presupuesto',
    'eliminar_presupuesto':   'finance.eliminar_presupuesto',
    'lista_facturas':         'finance.lista_facturas',
    'nueva_factura':          'finance.nueva_factura',
    'editar_factura':         'finance.editar_factura',
    'marcar_factura_pagada':  'finance.marcar_factura_pagada',
    'eliminar_factura':       'finance.eliminar_factura',
    'lista_servicios':        'finance.lista_servicios',
    'nuevo_servicio':         'finance.nuevo_servicio',
    'editar_servicio':        'finance.editar_servicio',
    'eliminar_servicio':      'finance.eliminar_servicio',
    'detalle_servicio':       'finance.detalle_servicio',
    'nuevo_pago_servicio':    'finance.nuevo_pago_servicio',
    'marcar_pago_pagado':     'finance.marcar_pago_pagado',
    'eliminar_pago_servicio': 'finance.eliminar_pago_servicio',

    # reports
    'reportes':                   'reports.reportes',
    'exportar_inventario_excel':  'reports.exportar_inventario_excel',
    'exportar_movimientos_excel': 'reports.exportar_movimientos_excel',
    'exportar_valorizacion_pdf':  'reports.exportar_valorizacion_pdf',

    # api (solo los que aparecen en templates)
    'api_alertas_stock_bajo': 'api.api_alertas_stock_bajo',
    'api_buscar_productos':   'api.api_buscar_productos',
    'api_finanzas_mensual':   'api.api_finanzas_mensual',
}


def _replace_in_content(content: str) -> tuple[str, int]:
    """Reemplaza url_for('old') → url_for('blueprint.new') en el contenido."""
    changes = 0
    for old, new in ENDPOINT_MAP.items():
        # Maneja comillas simples y dobles: url_for('old') y url_for("old")
        for q in ("'", '"'):
            old_pat = f"url_for({q}{old}{q}"
            new_str = f"url_for({q}{new}{q}"
            if old_pat in content:
                content = content.replace(old_pat, new_str)
                changes += 1
            # Con parámetros: url_for('old', id=x) — el nombre siempre está entre comillas
            # ya se captura porque solo reemplazamos el nombre del endpoint
        # Jinja2 redirect() en templates: redirect(url_for(...)) ya cubierto
    return content, changes


def process_files(dry_run: bool = False):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Templates HTML/Jinja2
    template_files = glob.glob(os.path.join(base, 'templates', '**', '*.html'), recursive=True)
    # Python blueprints y helpers
    py_files = glob.glob(os.path.join(base, 'app', '**', '*.py'), recursive=True)

    all_files = template_files + py_files
    total_changes = 0

    for filepath in sorted(all_files):
        with open(filepath, encoding='utf-8') as f:
            original = f.read()

        updated, changes = _replace_in_content(original)

        if changes > 0:
            rel = os.path.relpath(filepath, base)
            print(f"[{changes:3d} cambios] {rel}")
            total_changes += changes
            if not dry_run:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(updated)

    print(f"\nTotal: {total_changes} reemplazos en {len(all_files)} archivos.")
    if dry_run:
        print("(dry-run — no se escribió nada)")


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    process_files(dry_run=dry_run)
