"""IRIS IDE companion 80:20 — 듀얼 타일 + 단일 창 셸."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMainWindow

from iris.system.ide_tiler import (
    compute_tile_rects,
    read_qt_window_rect,
    tiles_are_flush,
    tiles_have_overlap,
    tile_iris_ide_and_iris,
    work_area_for,
)
from iris.ui.workspaces.ide_companion_page import IdeCompanionPage, IdeUnifiedShell
from iris.ui.workspaces.iris_ide_window import IrisIdeWindow


def main() -> int:
    from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

    ensure_qt_webengine_ready()
    app = QApplication.instance() or QApplication(sys.argv)
    iris = QMainWindow()
    iris.setWindowTitle("Iris Light")
    iris.resize(900, 700)
    iris.show()
    ide = IrisIdeWindow()
    ide.show()
    app.processEvents()

    area = work_area_for(iris)
    tiles = compute_tile_rects(area, ide_ratio=0.8)
    assert tiles_are_flush(tiles.ide, tiles.iris)
    assert tiles.ide.width() + tiles.iris.width() == area.width()

    ok, err = tile_iris_ide_and_iris(ide, iris, ide_ratio=0.8)
    assert ok, err
    app.processEvents()

    ide_geo = read_qt_window_rect(ide) or ide.geometry()
    iris_geo = read_qt_window_rect(iris) or iris.geometry()
    total = area.width()
    expected_ide = int(total * 0.8)
    assert ide_geo.width() == expected_ide, (ide_geo.width(), expected_ide)
    assert iris_geo.width() == total - expected_ide, (iris_geo.width(), total - expected_ide)
    assert tiles_are_flush(ide_geo, iris_geo), (ide_geo, iris_geo)
    assert not tiles_have_overlap(ide_geo, iris_geo), (ide_geo, iris_geo)
    assert ide_geo.width() + iris_geo.width() == total

    # 단일 창 내부 8:2
    shell = IdeUnifiedShell()
    companion = IdeCompanionPage()
    ide2 = IrisIdeWindow()
    ide2.set_embedded(True)
    shell.resize(1000, 600)
    shell.show()
    shell.mount(ide2, companion, total_w=1000)
    app.processEvents()
    sizes = shell._split.sizes()
    assert sizes[0] == 800 and sizes[1] == 200, sizes
    assert ide2.is_embedded()

    iris.close()
    app.processEvents()
    print("iris_ide_companion_tile check ok", tiles.ide, tiles.iris, "unified", sizes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
