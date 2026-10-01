"""IRIS IDE window smoke check."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRect

from iris.system.ide_tiler import compute_tile_rects, tiles_are_flush
from iris.ui.window.frameless_chrome import FramelessShell
from iris.ui.workspaces.iris_ide_window import IRIS_IDE_TITLE, IrisIdeWindow


def main() -> None:
    from PyQt6.QtWidgets import QApplication
    import sys

    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    work = QRect(0, 0, 1000, 800)
    tiles = compute_tile_rects(work, ide_ratio=0.8)
    assert tiles.ide.width() == 800
    assert tiles.iris.width() == 200
    assert tiles_are_flush(tiles.ide, tiles.iris)
    w = IrisIdeWindow()
    assert w.windowFlags() & Qt.WindowType.FramelessWindowHint
    shell = w.centralWidget()
    assert isinstance(shell, FramelessShell)
    assert len(shell._grips) == 8
    w.resize(800, 600)
    w.show()
    app.processEvents()
    body = shell._content
    assert body is not None
    assert body.geometry().x() == shell._margin and body.geometry().y() == shell._margin
    assert not body.geometry().intersects(shell._grips[4].geometry())
    assert w._caption.isVisible()
    assert w.maximize_button_global_rect().width() == 34
    w.show_loading()
    assert w.is_opening()
    assert not w.is_theia_loaded()
    assert w.windowTitle() == IRIS_IDE_TITLE
    app.quit()
    print("iris_ide_window check ok")


if __name__ == "__main__":
    main()
