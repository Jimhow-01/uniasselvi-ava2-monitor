"""Fixtures: nenhum teste escreve no diretorio real do app.

config.py calcula APP_DIR/CONFIG_PATH/STATE_PATH no momento do import, e os
modulos derivados (watcher, instance) copiam esses caminhos para nomes proprios.
Por isso o monkeypatch precisa atingir CADA copia, nao so config.
"""
import pytest


@pytest.fixture(autouse=True)
def isolate_app_paths(tmp_path, monkeypatch):
    """Redireciona todos os caminhos de runtime para tmp_path."""
    from uniasselvi import config, instance, watcher

    monkeypatch.setattr(config, "APP_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"), raising=False)
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"), raising=False)
    monkeypatch.setattr(config, "_CRED_PATH", str(tmp_path / ".cred"), raising=False)

    monkeypatch.setattr(watcher, "STATE_PATH", str(tmp_path / "state.json"), raising=False)
    monkeypatch.setattr(instance, "PID_PATH", str(tmp_path / "monitor.pid"), raising=False)
    # sms.py e notifier.py derivam seus caminhos de config no momento do import,
    # entao cada copia precisa ser redirecionada tambem.
    from uniasselvi import notifier, sms

    monkeypatch.setattr(sms, "_CRED_PATH", str(tmp_path / ".cred_sms"), raising=False)
    monkeypatch.setattr(notifier, "ICON_PATH", str(tmp_path / "app.ico"), raising=False)

    yield
