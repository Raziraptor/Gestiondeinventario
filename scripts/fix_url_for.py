"""
Reemplaza url_for('endpoint') → url_for('blueprint.endpoint') en todos los templates.
Uso: python scripts/fix_url_for.py
"""
import os
import re

MAPPING = {
    'admin_panel':                   'admin.admin_panel',
    'admin_reset_password':          'admin.admin_reset_password',
    'aprobar_solicitud':             'purchasing.aprobar_solicitud',
    'asignar_producto_rapido':       'inventory.asignar_producto_rapido',
    'asignar_usuario':               'admin.asignar_usuario',
    'cancelar_orden':                'purchasing.cancelar_orden',
    'cancelar_proyecto_oc':          'purchasing.cancelar_proyecto_oc',
    'cerrar_centro_costo':           'finance.cerrar_centro_costo',
    'configurar_etiqueta':           'inventory.configurar_etiqueta',
    'configurar_etiqueta_diseno':    'inventory.configurar_etiqueta_diseno',
    'configurar_excel_diseno':       'inventory.configurar_excel_diseno',
    'configurar_plantilla':          'admin.configurar_plantilla',
    'dashboard':                     'main.dashboard',
    'descargar_template_importacion':'inventory.descargar_template_importacion',
    'detalle_centro_costo':          'finance.detalle_centro_costo',
    'detalle_servicio':              'finance.detalle_servicio',
    'editar_almacen':                'inventory.editar_almacen',
    'editar_categoria':              'inventory.editar_categoria',
    'editar_centro_costo':           'finance.editar_centro_costo',
    'editar_factura':                'finance.editar_factura',
    'editar_gasto':                  'finance.editar_gasto',
    'editar_orden':                  'purchasing.editar_orden',
    'editar_presupuesto':            'finance.editar_presupuesto',
    'editar_producto':               'inventory.editar_producto',
    'editar_proveedor':              'inventory.editar_proveedor',
    'editar_proyecto_oc':            'purchasing.editar_proyecto_oc',
    'editar_servicio':               'finance.editar_servicio',
    'eliminar_almacen':              'inventory.eliminar_almacen',
    'eliminar_categoria':            'inventory.eliminar_categoria',
    'eliminar_factura':              'finance.eliminar_factura',
    'eliminar_movimiento_salida':    'inventory.eliminar_movimiento_salida',
    'eliminar_orden':                'purchasing.eliminar_orden',
    'eliminar_pago_servicio':        'finance.eliminar_pago_servicio',
    'eliminar_presupuesto':          'finance.eliminar_presupuesto',
    'eliminar_producto_de_almacen':  'inventory.eliminar_producto_de_almacen',
    'eliminar_servicio':             'finance.eliminar_servicio',
    'enviar_orden':                  'purchasing.enviar_orden',
    'enviar_proyecto_oc':            'purchasing.enviar_proyecto_oc',
    'exportar_gastos_excel':         'reports.exportar_gastos_excel',
    'exportar_hd_csv':               'purchasing.exportar_hd_csv',
    'exportar_inventario_excel':     'reports.exportar_inventario_excel',
    'exportar_movimientos_excel':    'reports.exportar_movimientos_excel',
    'exportar_proyecto_hd_csv':      'purchasing.exportar_proyecto_hd_csv',
    'exportar_proyectos_oc_excel':   'reports.exportar_proyectos_oc_excel',
    'exportar_valorizacion_pdf':     'reports.exportar_valorizacion_pdf',
    'finanzas_dashboard':            'finance.finanzas_dashboard',
    'forgot_password':               'auth.forgot_password',
    'generar_etiqueta_personalizada':'inventory.generar_etiqueta_personalizada',
    'generar_oc_pdf':                'purchasing.generar_oc_pdf',
    'generar_proyecto_oc_pdf':       'purchasing.generar_proyecto_oc_pdf',
    'generar_salida_pdf':            'inventory.generar_salida_pdf',
    'gestionar_inventario_almacen':  'inventory.gestionar_inventario_almacen',
    'guardar_integracion_hd':        'inventory.guardar_integracion_hd',
    'historial_actividad':           'main.historial_actividad',
    'historial_producto':            'inventory.historial_producto',
    'historial_salidas':             'inventory.historial_salidas',
    'importar_productos':            'inventory.importar_productos',
    'index':                         'main.index',
    'lista_almacenes':               'inventory.lista_almacenes',
    'lista_aprobaciones':            'purchasing.lista_aprobaciones',
    'lista_categorias':              'inventory.lista_categorias',
    'lista_centros_costo':           'finance.lista_centros_costo',
    'lista_facturas':                'finance.lista_facturas',
    'lista_gastos':                  'finance.lista_gastos',
    'lista_movimientos':             'inventory.lista_movimientos',
    'lista_ordenes':                 'purchasing.lista_ordenes',
    'lista_presupuestos':            'finance.lista_presupuestos',
    'lista_productos_sin_almacen':   'inventory.lista_productos_sin_almacen',
    'lista_proveedores':             'inventory.lista_proveedores',
    'lista_proyectos_oc':            'purchasing.lista_proyectos_oc',
    'lista_servicios':               'finance.lista_servicios',
    'login':                         'auth.login',
    'logout':                        'auth.logout',
    'manual_usuario':                'admin.manual_usuario',
    'marcar_factura_pagada':         'finance.marcar_factura_pagada',
    'marcar_pago_pagado':            'finance.marcar_pago_pagado',
    'nueva_categoria':               'inventory.nueva_categoria',
    'nueva_factura':                 'finance.nueva_factura',
    'nueva_orden':                   'purchasing.nueva_orden',
    'nueva_orden_manual':            'purchasing.nueva_orden_manual',
    'nueva_organizacion':            'admin.nueva_organizacion',
    'nueva_proyecto_oc':             'purchasing.nueva_proyecto_oc',
    'nueva_transferencia':           'inventory.nueva_transferencia',
    'nuevo_ajuste':                  'inventory.nuevo_ajuste',
    'nuevo_almacen':                 'inventory.nuevo_almacen',
    'nuevo_centro_costo':            'finance.nuevo_centro_costo',
    'nuevo_gasto':                   'finance.nuevo_gasto',
    'nuevo_pago_servicio':           'finance.nuevo_pago_servicio',
    'nuevo_presupuesto':             'finance.nuevo_presupuesto',
    'nuevo_producto':                'inventory.nuevo_producto',
    'nuevo_proveedor':               'inventory.nuevo_proveedor',
    'nuevo_proyecto_oc':             'purchasing.nuevo_proyecto_oc',
    'nuevo_servicio':                'finance.nuevo_servicio',
    'rechazar_solicitud':            'purchasing.rechazar_solicitud',
    'recibir_orden':                 'purchasing.recibir_orden',
    'recibir_proyecto_oc':           'purchasing.recibir_proyecto_oc',
    'register':                      'auth.register',
    'registrar_salida':              'inventory.registrar_salida',
    'reportes':                      'reports.reportes',
    'reset_password':                'auth.reset_password',
    'solicitar_aprobacion_oc':       'purchasing.solicitar_aprobacion_oc',
    'subir_hd_auto':                 'purchasing.subir_hd_auto',
    'super_admin':                   'admin.super_admin',
    'ver_orden':                     'purchasing.ver_orden',
    'ver_proyecto_oc':               'purchasing.ver_proyecto_oc',
    'ver_salida':                    'inventory.ver_salida',
}

# Regex: url_for( followed by quote, then endpoint name (no dot), then quote
# Handles both ' and " quotes
PATTERN = re.compile(r"""url_for\((['"])([a-zA-Z_][a-zA-Z0-9_]*)(\1)""")


def replace_in_content(content, filepath):
    changes = []

    def replacer(m):
        quote = m.group(1)
        endpoint = m.group(2)
        if endpoint in MAPPING:
            new_ep = MAPPING[endpoint]
            changes.append(f'  {endpoint!r} -> {new_ep!r}')
            return f"url_for({quote}{new_ep}{quote}"
        return m.group(0)  # no change if not in mapping

    new_content = PATTERN.sub(replacer, content)
    return new_content, changes


def process_templates(templates_dir):
    total_files = 0
    total_changes = 0

    for root, dirs, files in os.walk(templates_dir):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, encoding='utf-8') as f:
                original = f.read()

            new_content, changes = replace_in_content(original, fpath)

            if changes:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                rel = os.path.relpath(fpath, templates_dir)
                print(f'UPDATED {rel} ({len(changes)} replacements)')
                for c in changes:
                    print(c)
                total_files += 1
                total_changes += len(changes)

    print(f'\nDone: {total_changes} replacements in {total_files} files.')


if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates_dir = os.path.join(base, 'templates')
    process_templates(templates_dir)
