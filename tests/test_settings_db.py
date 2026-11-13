from olvgl.infrastructure.settings_db import SettingsDB


def test_settings_and_recent(tmp_path):
    db = SettingsDB(str(tmp_path / "studio.db"))
    assert db.get("zoom", 1.0) == 1.0
    db.set("zoom", 2.5)
    db.set("geometry", {"w": 10})
    assert db.get("zoom") == 2.5 and db.get("geometry") == {"w": 10}
    files = []
    for i in range(3):
        f = tmp_path / f"p{i}.olvgl"
        f.write_text("{}")
        files.append(str(f))
        db.add_recent(str(f), f"P{i}")
    db.add_recent(str(tmp_path / "borrado.olvgl"))
    recent = db.recent()
    assert [p for p, _ in recent] == list(reversed(files))
    db.add_recent(files[0])
    assert db.recent(limit=1)[0][0] == files[0]
    db.remove_recent(files[0])
    assert files[0] not in [p for p, _ in db.recent()]
    db.close()
    db2 = SettingsDB(str(tmp_path / "studio.db"))
    assert db2.get("zoom") == 2.5
    db2.close()
