import pytest

COMANDOS = ['fix-incidencias-v3', 'limpiar-incidencias-cerradas']


def test_comandos_registrados(app):
    assert set(COMANDOS) <= set(app.cli.commands)


@pytest.mark.parametrize('comando', COMANDOS)
def test_help_sale_con_cero(app, comando):
    r = app.test_cli_runner().invoke(args=[comando, '--help'])
    assert r.exit_code == 0, r.output
    assert 'Usage' in r.output


def test_retencion_dry_run_por_cli(app):
    r = app.test_cli_runner().invoke(args=['limpiar-incidencias-cerradas', '--dry-run'])
    assert r.exit_code == 0, r.output
    assert 'limpiar-incidencias-cerradas (dry-run): por_avisar=0' in r.output
