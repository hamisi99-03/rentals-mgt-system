"""Desktop launcher: run Django locally with waitress and open a pywebview window."""

import os
import socket
import sys
import threading

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("RENTALS_DEBUG", "0")

PORT_RANGE = (8765, 8865)


def find_free_port():
    for port in range(*PORT_RANGE):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main():
    import django

    django.setup()

    from pathlib import Path

    from django.conf import settings
    from django.core.management import call_command

    from core.backup import needs_daily_backup, perform_backup

    # Back up the live database before applying any migrations.
    db_path = Path(settings.DATABASES["default"]["NAME"])
    if db_path.exists():
        try:
            perform_backup(reason="pre-migrate")
        except Exception:
            # Never block startup on a backup problem; the app can still migrate.
            pass

    call_command("migrate", interactive=False, verbosity=0)

    if needs_daily_backup():
        perform_backup(reason="daily-startup")

    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application
    from waitress import create_server

    port = find_free_port()
    application = StaticFilesHandler(get_wsgi_application())
    server = create_server(application, host="127.0.0.1", port=port, threads=6)
    thread = threading.Thread(target=server.run, name="rentals-web", daemon=True)
    thread.start()

    import webview

    window = webview.create_window(
        "Rental Manager",
        f"http://127.0.0.1:{port}/",
        width=1280,
        height=820,
        min_size=(1024, 680),
        text_select=True,
    )
    try:
        webview.start()
    finally:
        perform_backup(reason="app-exit")
        server.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
