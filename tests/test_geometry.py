import pytest
from mchanhua.geometry import (
    Region,
    follow_cursor_region,
    logical_to_physical,
    normalize_drag,
)


def test_region_csv_round_trip():
    region = Region(10, 20, 300, 120)
    assert region.to_csv() == "10,20,300,120"
    assert Region.parse("10,20,300,120") == region
    assert Region.parse(" 10, 20 ,300,120 ") == region
    assert Region.parse("10，20，300，120") == region
    assert Region.parse([10, 20, 300, 120]) == region


def test_region_rejects_bad_input():
    with pytest.raises(ValueError):
        Region(0, 0, 0, 10)
    with pytest.raises(ValueError):
        Region(0, 0, 10, -5)
    with pytest.raises(TypeError):
        Region(0, 0, True, 10)
    with pytest.raises(ValueError):
        Region.parse("1,2,3")
    with pytest.raises(ValueError):
        Region.parse("a,b,c,d")
    with pytest.raises(ValueError):
        Region.parse("1,2,3,4,5")


def test_region_geometry_helpers():
    region = Region(100, 100, 200, 100)
    assert region.right == 300
    assert region.bottom == 200
    assert region.area == 20000
    assert region.center == (200.0, 150.0)
    assert region.contains(150, 150)
    assert not region.contains(300, 150)
    assert region.moved(-50, 25).to_csv() == "50,125,200,100"
    assert region.scaled(2).to_csv() == "200,200,400,200"


def test_region_clamp_and_intersect():
    screen = Region(0, 0, 2560, 1440)
    assert Region(-100, -50, 500, 400).clamp(screen).to_csv() == "0,0,400,350"
    assert Region(2500, 1400, 500, 500).clamp(screen).to_csv() == "2500,1400,60,40"
    assert Region(100, 100, 100, 100).intersect(Region(150, 150, 100, 100)).to_csv() == "150,150,50,50"
    assert Region(0, 0, 10, 10).intersect(Region(100, 100, 10, 10)) is None
    with pytest.raises(ValueError):
        Region(5000, 5000, 100, 100).clamp(screen)
    assert Region.to_mss(Region(1, 2, 3, 4)) == {"left": 1, "top": 2, "width": 3, "height": 4}


def test_follow_cursor_region_offsets_and_clamps():
    screen = Region(0, 0, 2560, 1440)
    offset = Region(-20, -10, 420, 320)
    assert follow_cursor_region(offset, (1000, 800), screen).to_csv() == "980,790,420,320"
    # 光标贴边时被裁到屏幕内
    assert follow_cursor_region(offset, (10, 5), screen).to_csv() == "0,0,410,315"


def test_logical_to_physical_handles_dpi_scale():
    physical = Region(0, 0, 2560, 1440)
    logical = Region(100, 100, 200, 100)
    # 逻辑 2048x1152（125% 缩放）→ 物理 2560x1440
    result = logical_to_physical(logical, (2048, 1152), physical)
    assert result.to_csv() == "125,125,250,125"
    with pytest.raises(ValueError):
        logical_to_physical(logical, (0, 0), physical)


def test_normalize_drag_supports_reverse_direction():
    assert normalize_drag(300, 200, 100, 50).to_csv() == "100,50,200,150"
    assert normalize_drag(100, 50, 300, 200).to_csv() == "100,50,200,150"
    with pytest.raises(ValueError):
        normalize_drag(100, 50, 100, 200)
