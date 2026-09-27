import pytest

from mchanhua.geometry import Region


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

