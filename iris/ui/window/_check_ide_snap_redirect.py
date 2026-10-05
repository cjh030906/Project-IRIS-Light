"""IDE 포커스의 Win+방향키가 아이리스 배치로 가는지."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.window.ide_snap_redirect import (
    VK_LEFT,
    VK_RIGHT,
    VK_UP,
    SnapMemory,
    SnapStep,
    apply_snap,
    classify_zone,
    next_snap,
    shift_monitor,
    should_take_snap,
    title_is_iris_ide,
    zone_rect,
)
from iris.ui.window.ide_snap_redirect import IdeSnapRedirect


def _work() -> QRect:
    return QRect(0, 0, 1000, 800)


def _check_zones() -> None:
    work = _work()
    normal = QRect(100, 80, 400, 300)
    assert classify_zone(work, normal, maximized=False) == "normal"
    assert classify_zone(work, zone_rect(work, "left"), maximized=False) == "left"
    assert classify_zone(work, zone_rect(work, "br"), maximized=False) == "br"
    assert classify_zone(work, normal, maximized=True) == "max"


def _check_keyboard_cycle() -> None:
    work = _work()
    memory = SnapMemory()
    normal = QRect(100, 80, 400, 300)
    step = next_snap(work, normal, "left", maximized=False, memory=memory)
    assert step == SnapStep("geometry", zone_rect(work, "left"))
    assert memory.restore == normal
    step = next_snap(work, step.rect, "up", maximized=False, memory=memory)
    assert step.rect == zone_rect(work, "tl")
    step = next_snap(work, step.rect, "down", maximized=False, memory=memory)
    assert step.rect == zone_rect(work, "left")
    step = next_snap(work, step.rect, "right", maximized=False, memory=memory)
    assert step.rect == normal
    step = next_snap(work, normal, "up", maximized=False, memory=memory)
    assert step.kind == "maximize"
    step = next_snap(work, normal, "down", maximized=True, memory=memory)
    assert step.rect == normal
    step = next_snap(work, normal, "down", maximized=False, memory=memory)
    assert step.kind == "minimize"
    step = next_snap(work, zone_rect(work, "right"), "left", maximized=False, memory=memory)
    assert step.rect == memory.restore


def _check_shift_monitor() -> None:
    here = QRect(0, 0, 1000, 800)
    right = QRect(1000, 0, 800, 600)
    window = QRect(100, 40, 400, 300)
    moved = shift_monitor(window, "right", [here, right])
    assert moved is not None and moved.left() == 1100 and moved.width() == 400
    assert shift_monitor(window, "left", [here, right]) is None
    assert shift_monitor(window, "right", [here]) is None


def _check_take_rules() -> None:
    assert should_take_snap(VK_LEFT, win=True, ctrl=False, alt=False, ide_foreground=True)
    assert not should_take_snap(VK_LEFT, win=True, ctrl=False, alt=False, ide_foreground=False)
    assert not should_take_snap(VK_LEFT, win=False, ctrl=False, alt=False, ide_foreground=True)
    assert not should_take_snap(VK_LEFT, win=True, ctrl=True, alt=False, ide_foreground=True)
    assert not should_take_snap(VK_UP, win=True, ctrl=False, alt=True, ide_foreground=True)
    assert not should_take_snap(0x41, win=True, ctrl=False, alt=False, ide_foreground=True)
    assert title_is_iris_ide("IRIS IDE")
    assert title_is_iris_ide("readme.md — IRIS IDE")
    assert not title_is_iris_ide("")
    assert not title_is_iris_ide("Iris Light")


class _Owner(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.steps: list[SnapStep] = []
        self.locked = 0
        self.recorded = 0


def _check_repeat_swallows_once() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    owner = _Owner()
    owner.setGeometry(100, 80, 400, 300)
    redirect = IdeSnapRedirect(owner, ide_hwnd=lambda: 1, on_applied=lambda: None, arm_lock=lambda: None)
    queued: list[str] = []
    redirect._queue = lambda direction, shift: queued.append(direction)  # type: ignore[method-assign]
    assert redirect.consider(
        VK_RIGHT, False, win=True, ctrl=False, alt=False, shift=False, ide_foreground=True
    )
    assert queued == ["right"]
    assert redirect.consider(
        VK_RIGHT, False, win=True, ctrl=False, alt=False, shift=False, ide_foreground=True
    )
    assert queued == ["right"]
    assert redirect.consider(
        VK_RIGHT, True, win=True, ctrl=False, alt=False, shift=False, ide_foreground=True
    )
    assert redirect.consider(
        VK_LEFT, False, win=True, ctrl=True, alt=False, shift=False, ide_foreground=True
    ) is False
    del app


def _check_apply_geometry() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    host = QWidget()
    host.setGeometry(10, 10, 200, 100)
    target = QRect(0, 0, 500, 800)
    apply_snap(host, SnapStep("geometry", target))
    assert host.geometry() == target
    apply_snap(host, SnapStep("none"))
    assert host.geometry() == target
    del app


def main() -> None:
    _check_zones()
    _check_keyboard_cycle()
    _check_shift_monitor()
    _check_take_rules()
    _check_repeat_swallows_once()
    _check_apply_geometry()
    print("ide_snap_redirect check ok")


if __name__ == "__main__":
    main()
