import pytest

from neko import region


def test_using_restores_the_region_it_replaced():
    with region.using("jp"):
        with region.using("tw"):
            pass

        assert region.current() == "jp"


def test_using_rejects_an_unknown_region():
    with pytest.raises(ValueError):
        with region.using("de"):
            pass


def test_data_files_are_scoped_by_the_active_region():
    with region.using("kr"):
        assert region.data_path("units.json").parent.name == "kr"
