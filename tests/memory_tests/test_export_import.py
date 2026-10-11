# Tests for data portability (JSON export/import)

import pytest
import tempfile
import json
from memory.manager import MemoryManager
from memory.exceptions import MemoryError_


class TestExportImport:
    def test_export_import_roundtrip(self, mm, tmp_path):
        export_path = str(tmp_path / "export.json")
        
        # Add data
        mm.add("Fact One", category="preference", sensitivity=1)
        mm.add("Fact Two", category="other")
        mm.add_entity("Name", type="person", aliases=["alias"])
        mm.add_episode("Summary of things")
        
        # Export
        n_exp = mm.export_json(export_path)
        assert n_exp > 0
        
        # New manager import
        import_db = str(tmp_path / "import.db")
        new_mm = MemoryManager(db_path=import_db)
        
        n_imp = new_mm.import_json(export_path)
        assert n_imp == n_exp
        
        # Verify data
        facts = new_mm.list()
        assert len(facts) == 2
        assert any(f.content == "Fact One" and f.sensitivity == 1 for f in facts)
        
        ents = new_mm.entity_list()
        assert len(ents) == 1
        assert ents[0]["name"] == "Name"
        
        new_mm.close()
        
    def test_import_corrupted_file(self, mm, tmp_path):
        corrupt_path = str(tmp_path / "corrupt.json")
        with open(corrupt_path, "w", encoding="utf-8") as f:
            f.write("invalid json {")
            
        with pytest.raises(MemoryError_):
            mm.import_json(corrupt_path)

    def test_import_skips_invalid_records(self, mm, tmp_path):
        import_path = str(tmp_path / "bad.json")
        data = {
            "version": 1,
            "facts": [{"content": ""}, {"content": "Valid Fact"}],
            "entities": [{"bad": "data"}],
            "episodes": [],
        }
        with open(import_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
            
        n = mm.import_json(import_path)
        assert n == 1
        facts = mm.list()
        assert len(facts) == 1
        assert facts[0].content == "Valid Fact"
