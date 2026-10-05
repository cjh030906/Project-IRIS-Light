# iris_ide_runtime

`iris/system/iris_ide_runtime.py`

IRIS IDE (Eclipse Theia) runtime — install, start, bridge, shutdown.

## 주요 정의

- `def is_iris_ide_demo`
- `def runtime_source_dir`
- `def runtime_install_dir`
- `def runtime_state_path`
- `def iris_ide_config_dir`
- `def _free_port`
- `class IrisIdeStatus`
- `def _yarn_needs_native_bypass`
- `class IrisIdeRuntimeManager`
- `def shared_iris_ide_runtime`
- `def _self_check`

## 내부 의존성

- [[hermes_iris_control_sync]]
- [[node_runtime]]
