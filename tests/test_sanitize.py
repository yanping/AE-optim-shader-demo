import tempfile
from pathlib import Path
from scripts.mask_credentials import (
    extract_current_credentials,
    mask_files,
    restore_files,
    PROJECT_ID_PLACEHOLDER,
    GE_APP_ID_PLACEHOLDER,
)


def test_extract_and_mask_credentials():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("""gcp:
  project_id: "test-proj-123"
  ge_app_id: "test-app-456"
""", encoding="utf-8")

        pid, app = extract_current_credentials(cfg)
        assert pid == "test-proj-123"
        assert app == "test-app-456"

        # Test masking
        mods = mask_files(tmp_path, pid, app, dry_run=False)
        assert cfg in mods
        masked_content = cfg.read_text(encoding="utf-8")
        assert PROJECT_ID_PLACEHOLDER in masked_content
        assert GE_APP_ID_PLACEHOLDER in masked_content
        assert "test-proj-123" not in masked_content

        # Test restore
        mods_restore = restore_files(tmp_path, "restored-proj", "restored-app", dry_run=False)
        assert cfg in mods_restore
        restored_content = cfg.read_text(encoding="utf-8")
        assert "restored-proj" in restored_content
        assert "restored-app" in restored_content
