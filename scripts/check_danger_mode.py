import app.config as config
from app.utils.screenshots import is_chrome_debug_port_open
from scripts.update_chrome_shortcut import shortcuts_need_patch


def main() -> int:
    ready = is_chrome_debug_port_open("127.0.0.1", config.DANGER_PORT)
    if ready:
        print("Danger mode detected.")
    else:
        print("Danger mode not detected.")

    patched = not shortcuts_need_patch()
    if patched:
        print("Chrome shortcuts are patched.")
    else:
        print("Chrome shortcuts need patching.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
