# Tests for entities CRUD and entity_list() compatibility with Phase 1

import pytest
from memory.manager import MemoryManager
from memory.exceptions import EntityNotFound, ValidationError


class TestEntityCRUD:
    def test_add_entity(self, mm):
        e = mm.add_entity("Rahul", type="person", aliases=["राहुल", "Rahool"])
        assert e.id > 0
        assert e.name == "Rahul"
        assert e.type == "person"
        assert "राहुल" in e.aliases
        assert "Rahool" in e.aliases

    def test_add_entity_default_type(self, mm):
        e = mm.add_entity("Delhi")
        assert e.type == "person"

    def test_add_entity_empty_name_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add_entity("")

    def test_add_entity_whitespace_name_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add_entity("   ")

    def test_update_entity_name(self, mm):
        e = mm.add_entity("Rahu")
        updated = mm.update_entity(e.id, name="Rahul")
        assert updated.name == "Rahul"

    def test_update_entity_aliases(self, mm):
        e = mm.add_entity("Rahul")
        updated = mm.update_entity(e.id, aliases=["राहुल", "Rahool"])
        assert "राहुल" in updated.aliases

    def test_update_entity_type(self, mm):
        e = mm.add_entity("Delhi")
        updated = mm.update_entity(e.id, type="place")
        assert updated.type == "place"

    def test_update_entity_missing_raises(self, mm):
        with pytest.raises(EntityNotFound):
            mm.update_entity(99999, name="X")

    def test_delete_entity(self, mm):
        e = mm.add_entity("ToDelete")
        mm.delete_entity(e.id)
        with pytest.raises(EntityNotFound):
            mm.update_entity(e.id, name="Gone")

    def test_delete_entity_missing_raises(self, mm):
        with pytest.raises(EntityNotFound):
            mm.delete_entity(99999)


class TestEntityList:
    def test_entity_list_format(self, mm):
        mm.add_entity("Rahul", type="person", aliases=["राहुल"])
        mm.add_entity("Delhi", type="place", aliases=["दिल्ली"])
        elist = mm.entity_list()
        assert len(elist) == 2

        # Check format matches Phase 1 sanitize() expected input
        for e in elist:
            assert "name" in e
            assert "aliases" in e
            assert "type" in e
            assert isinstance(e["aliases"], list)

    def test_entity_list_works_with_sanitize(self, mm):
        """entity_list() output must work directly with privacy.sanitize()."""
        mm.add_entity("Vikram", type="person", aliases=["विक्रम"])
        elist = mm.entity_list()

        from privacy import sanitize
        result = sanitize("Vikram went to the market", entities=elist)
        assert "Vikram" not in result.clean_text
        assert "[PERSON_1]" in result.clean_text

    def test_entity_list_hindi_name_with_sanitize(self, mm):
        mm.add_entity("प्रियंका", type="person")
        elist = mm.entity_list()

        from privacy import sanitize
        result = sanitize("प्रियंका ने कहा कि", entities=elist)
        assert "प्रियंका" not in result.clean_text

    def test_entity_list_empty(self, mm):
        assert mm.entity_list() == []

    def test_entity_list_preserves_aliases(self, mm):
        mm.add_entity("Suresh", type="person", aliases=["सुरेश", "Suri"])
        elist = mm.entity_list()
        e = elist[0]
        assert "सुरेश" in e["aliases"]
        assert "Suri" in e["aliases"]
