"""IDE hero overlay + welcome + intro self-check."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from iris.ui.ide.iris_ide_hero_overlay import IrisIdeHeroOverlay
from iris.ui.ide.iris_ide_welcome_layer import IrisIdeWelcomeLayer
from iris.ui.sidebar.workspace_action_panel import WorkspaceActionPanel
from iris.ui.widgets.particle_visualizer import ParticleVisualizer
from iris.ui.widgets.visualizer import Visualizer
from iris.ui.window.startup_intro import StartupIntroAnimator
from iris.ui.workspaces.ide_companion_page import IdeUnifiedShell


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    hero = IrisIdeHeroOverlay()
    assert hero._title.text() == "IRIS IDE"
    assert hero.btn_open is not None

    layer = IrisIdeWelcomeLayer()
    assert layer._title.text() == "IRIS IDE"

    orb = ParticleVisualizer()
    orb.set_hero_mode(True)
    assert orb._hero_mode is True

    viz = Visualizer()
    viz.set_hero_orb_placement(True)
    assert viz._center_y_ratio > 0.36

    intro = StartupIntroAnimator()
    assert hasattr(intro, "start_panels_reveal")
    assert hasattr(intro, "start_exit_to_void")
    assert hasattr(intro, "start_hero_reveal")
    assert hasattr(intro, "start_hero_conceal")
    assert hasattr(intro, "start_enter_from_void")
    assert hasattr(intro, "restore_proxies")

    hits: list[str] = []
    panel = WorkspaceActionPanel()
    panel.set_default_callback(lambda: hits.append("default"))
    panel.add_icon_action(
        action_id="ide",
        icon_kind="ide",
        tooltip="IDE",
        callback=lambda: hits.append("ide"),
        reclick_returns=False,
    )
    panel.set_action_active("ide", True)
    panel._invoke_icon_action("ide", lambda: hits.append("ide"))
    assert hits == ["ide"], hits

    shell = IdeUnifiedShell()
    shell.resize(1000, 600)
    shell.show()
    app.processEvents()
    shell.apply_ratio(1000)
    app.processEvents()
    sizes = shell._split.sizes()
    assert sum(sizes) == 1000, sizes
    assert sizes[0] == 800, sizes
    assert sizes[1] == 200, sizes

    print("ide_hero ok")
    app.quit()


if __name__ == "__main__":
    main()
