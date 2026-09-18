"""Cross-platform desktop paths, preferences, logging, and release assets."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from factory.platform.logs import configure_file_logging
from factory.platform.paths import application_paths, ensure_user_dirs
from factory.platform.preferences import DesktopPreferences, load_preferences, save_preferences


class PlatformPathsTest(unittest.TestCase):
    def test_windows_uses_local_appdata_and_unicode_paths(self) -> None:
        paths = application_paths(
            platform_name="win32",
            environ={"LOCALAPPDATA": r"C:\Users\张三\AppData\Local"},
            home=Path(r"C:\Users\张三"),
        )
        self.assertEqual(paths.root, Path(r"C:\Users\张三\AppData\Local") / "StoryFactory")
        self.assertEqual(paths.projects.name, "projects")
        self.assertEqual(paths.log_file.name, "storyfactory.log")

    def test_windows_has_safe_fallback(self) -> None:
        home = Path(r"C:\Users\测试用户")
        paths = application_paths(platform_name="win32", environ={}, home=home)
        self.assertEqual(paths.root, home / "AppData" / "Local" / "StoryFactory")

    def test_macos_and_linux_locations(self) -> None:
        home = Path("/Users/example")
        mac = application_paths(platform_name="darwin", environ={}, home=home)
        linux = application_paths(
            platform_name="linux",
            environ={"XDG_DATA_HOME": "/data/用户"},
            home=Path("/home/example"),
        )
        self.assertEqual(mac.root, home / "Library" / "Application Support" / "StoryFactory")
        self.assertEqual(linux.root, Path("/data/用户") / "StoryFactory")

    def test_ensure_dirs_and_utf8_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = application_paths(
                platform_name="linux",
                environ={"XDG_DATA_HOME": raw},
                home=Path(raw),
            )
            ensure_user_dirs(paths)
            for folder in (paths.config, paths.logs, paths.cache, paths.projects, paths.database, paths.runtime):
                self.assertTrue(folder.is_dir())
            self.assertEqual(paths.settings_file.read_text(encoding="utf-8"), "{}\n")


class DesktopPreferencesTest(unittest.TestCase):
    def test_round_trip_unicode_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "配置" / "desktop.json"
            prefs = DesktopPreferences(
                project_path=r"D:\小说项目\仙侠小说",
                model_path=r"D:\AI\Models\Qwen",
                first_run=False,
            )
            save_preferences(prefs, path)
            loaded = load_preferences(path)
            self.assertEqual(loaded, prefs)
            blob = path.read_text(encoding="utf-8")
            self.assertIn("仙侠小说", blob)
            self.assertNotIn("api_key", blob.lower())

    def test_unknown_or_secret_fields_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "desktop.json"
            path.write_text(
                json.dumps({"language": "zh-CN", "api_key": "should-not-load"}),
                encoding="utf-8",
            )
            loaded = load_preferences(path)
            self.assertEqual(loaded.language, "zh-CN")
            self.assertFalse(hasattr(loaded, "api_key"))

    def test_invalid_json_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "desktop.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(load_preferences(path), DesktopPreferences())


class DesktopLoggingTest(unittest.TestCase):
    def test_rotating_utf8_log(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "日志" / "storyfactory.log"
            handler = configure_file_logging(path, max_bytes=200, backup_count=2)
            logger = logging.getLogger("test.desktop.logging")
            for index in range(20):
                logger.info("中文日志 %s %s", index, "内容" * 10)
            handler.flush()
            self.assertTrue(path.exists())
            self.assertTrue(path.with_name("storyfactory.log.1").exists())
            logging.getLogger().removeHandler(handler)
            handler.close()


class WindowsPackagingTest(unittest.TestCase):
    def test_release_files_have_required_settings(self) -> None:
        root = Path(__file__).resolve().parents[1]
        spec = (root / "StoryFactory.spec").read_text(encoding="utf-8")
        installer = (root / "installer" / "storyfactory.iss").read_text(encoding="utf-8")
        manifest = (root / "packaging" / "windows" / "storyfactory.manifest").read_text(encoding="utf-8")
        self.assertIn('console=False', spec)
        self.assertIn('name="StoryFactory"', spec)
        self.assertIn("app.ico", spec)
        self.assertIn("PerMonitorV2", manifest)
        self.assertIn('level="asInvoker"', manifest)
        self.assertIn("{autodesktop}", installer)
        self.assertIn("{group}", installer)
        self.assertNotIn("[UninstallDelete]", installer)
        self.assertTrue((root / "assets" / "icons" / "app.ico").is_file())


if __name__ == "__main__":
    unittest.main()
