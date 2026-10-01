import sys
from datetime import datetime
from pathlib import Path

import pytest

import app.blueprints.views as views
from app.blueprints.views import (
    LANDING_CONTENT_PROFILES,
    LANDING_MODE_PROFILES,
    _apply_scene_timing,
    _build_landing_events,
    _build_landing_scenes,
    _compose_profiled_scenes,
    _is_local_landing_source,
    _landing_breadth,
    _landing_lanes,
)
from app.landing_config import load_landing_config


@pytest.fixture(autouse=True)
def synthetic_landing_preferences(monkeypatch):
    monkeypatch.setenv(
        "GLIMPSER_LANDING_CONFIG",
        str(Path(__file__).parent / "fixtures" / "landing_policy.json"),
    )
    config = load_landing_config()
    monkeypatch.setattr(views, "LANDING_CONFIG", config)
    for key in config:
        if hasattr(views, key):
            monkeypatch.setattr(views, key, config[key])
    monkeypatch.setattr(
        sys.modules[__name__],
        "LANDING_CONTENT_PROFILES",
        config["LANDING_CONTENT_PROFILES"],
    )


def _scene(scene_id: str, group_name: str, lanes: tuple[str, ...], score: int) -> dict:
    return {
        "event_score": 0,
        "group_name": group_name,
        "hero": {
            "lanes": lanes,
            "last_screenshot_time": "2026-04-13 23:00:00",
            "name": scene_id,
        },
        "hero_score": score,
        "id": scene_id,
        "profile_score": score,
        "scene_score": score,
    }


def test_landing_lanes_tag_kenosha_as_regional() -> None:
    lanes = _landing_lanes(
        "KenoshaHarbor",
        {
            "groups": "",
            "url": "http://example.test/kenosha-harbor.jpg",
        },
    )

    assert "regional" in lanes


def test_landing_lanes_tag_winthrop_as_regional() -> None:
    lanes = _landing_lanes(
        "WinthropBuoy",
        {
            "groups": "",
            "url": "http://example.test/winthrop-buoy.jpg",
        },
    )

    assert "regional" in lanes


def test_landing_lanes_tag_faa_as_ops_and_scenic() -> None:
    lanes = _landing_lanes(
        "FAA",
        {
            "groups": "",
            "url": "http://example.test/faa.jpg",
        },
    )

    assert "ops" in lanes
    assert "scenic" in lanes


def test_landing_breadth_is_profile_driven_not_mode_driven() -> None:
    expected = {
        "public": (2, 3),
        "kitchen": (4, 32),
        "living": (4, 36),
        "office": (6, 56),
        "hal": (6, 80),
    }

    for profile_name, breadth in expected.items():
        low = _landing_breadth(
            LANDING_MODE_PROFILES["low"],
            LANDING_CONTENT_PROFILES[profile_name],
        )
        ultra = _landing_breadth(
            LANDING_MODE_PROFILES["ultra"],
            LANDING_CONTENT_PROFILES[profile_name],
        )
        assert low == breadth
        assert ultra == breadth


def test_local_landing_source_treats_kenosha_as_trusted_regional_feed() -> None:
    assert _is_local_landing_source(
        {
            "groups": "kenosha,regional,weather",
            "url": "https://www.weatherbug.com/weather-camera/?cam=KNOSH",
            "name": "Kenosha",
        }
    )


def test_local_landing_source_treats_winthrop_as_trusted_regional_feed() -> None:
    assert _is_local_landing_source(
        {
            "groups": "winthrop,regional,weather",
            "url": "https://example.test/winthrop.jpg",
            "name": "WinthropBuoy",
        }
    )


def test_hal_composition_caps_repeated_groups_and_keeps_regional_scene() -> None:
    scenes = [
        _scene("sitea-1", "sitea", ("retail",), 300),
        _scene("sitea-2", "sitea", ("retail",), 295),
        _scene("sitea-3", "sitea", ("retail",), 290),
        _scene("sitea-4", "sitea", ("retail",), 285),
        _scene("ops-1", "network", ("ops",), 280),
        _scene("science-1", "satellite", ("science",), 270),
        _scene("home-1", "siteb", ("home",), 260),
        _scene("regional-1", "kenosha", ("regional", "scenic"), 250),
        _scene("beach-1", "beach", ("beach",), 240),
        _scene("scenic-1", "sky", ("scenic",), 230),
    ]

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=8,
    )

    selected_groups = [scene["group_name"] for scene in selected]
    selected_lanes = [tuple(scene["hero"]["lanes"]) for scene in selected]

    assert selected_groups.count("sitea") <= 5
    assert any("regional" in lanes for lanes in selected_lanes)


def test_hal_composition_keeps_kenosha_and_sitec_anchors() -> None:
    scenes = [
        _scene("sitea-1", "sitea", ("retail",), 320),
        _scene("store-1", "store", ("retail",), 315),
        _scene("sitec-1", "sitec", ("retail",), 250),
        _scene("plants-1", "plants", ("plants",), 310),
        _scene("beach-1", "beach", ("beach",), 305),
        _scene("kenosha-1", "kenosha", ("regional", "scenic"), 245),
        _scene("home-1", "siteb", ("home",), 300),
        _scene("ops-1", "network", ("ops",), 295),
    ]

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=8,
    )

    selected_groups = {scene["group_name"] for scene in selected}

    assert "kenosha" in selected_groups
    assert "sitec" in selected_groups


def test_hal_plants_group_can_split_into_multiple_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "plants",
        [
            {"name": "WhiteGrowerOverhead"},
            {"name": "PurpleClonerWide"},
            {"name": "WhiteGrowerPod"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["hal"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_hal_garden_group_can_split_into_multiple_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "garden",
        [
            {"name": "TitanArumGarden"},
            {"name": "CircleGardenLive"},
            {"name": "BotanyPondUChicago"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["hal"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_hal_siteb_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "siteb",
        [
            {"name": "HubitatExterior"},
            {"name": "HubitatMotion"},
            {"name": "HubitatPower"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["hal"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_hal_beach_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "beach",
        [
            {"name": "Northwestern"},
            {"name": "Edgewater"},
            {"name": "IceCover"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["hal"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_hal_beachhouse_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "beachhouse",
        [
            {"name": "BeachMapleTree"},
            {"name": "BeachFrontYard"},
            {"name": "BeachShore"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["hal"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_office_composition_keeps_regional_and_plants_in_rotation() -> None:
    scenes = [
        _scene("ops-1", "network", ("ops",), 300),
        _scene("home-1", "siteb", ("home",), 290),
        _scene("science-1", "satellite", ("science",), 280),
        _scene("regional-1", "kenosha", ("regional", "scenic"), 270),
        _scene("plants-1", "plants", ("plants",), 260),
        _scene("retail-1", "store", ("retail",), 250),
        _scene("scenic-1", "sky", ("scenic",), 240),
    ]

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=7,
    )

    selected_lanes = {lane for scene in selected for lane in scene["hero"]["lanes"]}

    assert {"ops", "home", "science", "regional", "plants"} <= selected_lanes


def test_office_siteb_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "siteb",
        [
            {"name": "HubitatExterior"},
            {"name": "HubitatMotion"},
            {"name": "HubitatPower"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["office"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_office_network_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "network",
        [
            {"name": "WiFi"},
            {"name": "BandwidthTX"},
            {"name": "BandwidthRX"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["office"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_office_beachhouse_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "beachhouse",
        [
            {"name": "BeachShore"},
            {"name": "BeachDriveway"},
            {"name": "BeachPathway"},
        ],
        scene_size=6,
        content=views.LANDING_CONTENT_PROFILES["office"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_hal_camera_minimums_keep_hubitat_views_when_available() -> None:
    scenes = [
        _scene("hubitat-motion", "siteb", ("home", "ops"), 320),
        _scene("hubitat-power", "siteb", ("home", "ops"), 315),
        _scene("hubitat-control", "siteb", ("home", "ops"), 310),
        _scene("hubitat-exterior", "siteb", ("home", "ops"), 305),
        _scene("hubitat-security", "siteb", ("home", "ops"), 300),
    ]
    hero_names = [
        "HubitatMotion",
        "HubitatPower",
        "HubitatControlPanel",
        "HubitatExterior",
        "HubitatSecurity",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=5,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_hal_camera_minimums_keep_hubitat_network_when_available() -> None:
    scenes = [
        _scene("hubitat-motion", "siteb", ("home", "ops"), 320),
        _scene("hubitat-power", "siteb", ("home", "ops"), 315),
        _scene("hubitat-control", "siteb", ("home", "ops"), 310),
        _scene("hubitat-exterior", "siteb", ("home", "ops"), 305),
        _scene("hubitat-security", "siteb", ("home", "ops"), 300),
        _scene("hubitat-network", "siteb", ("home", "ops"), 295),
        _scene("hubitat-media", "siteb", ("home", "ops"), 290),
        _scene("hubitat-main", "siteb", ("home", "ops"), 285),
    ]
    hero_names = [
        "HubitatMotion",
        "HubitatPower",
        "HubitatControlPanel",
        "HubitatExterior",
        "HubitatSecurity",
        "HubitatNetwork",
        "HubitatMedia",
        "HubitatMain",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=8,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_hal_distributes_siteb_scenes_through_rundown() -> None:
    scenes = [
        _scene("hubitat-motion", "siteb", ("home", "ops"), 320),
        _scene("hubitat-power", "siteb", ("home", "ops"), 315),
        _scene("hubitat-control", "siteb", ("home", "ops"), 310),
        _scene("hubitat-exterior", "siteb", ("home", "ops"), 305),
        _scene("hubitat-security", "siteb", ("home", "ops"), 300),
        _scene("hubitat-network", "siteb", ("home", "ops"), 295),
        _scene("hubitat-media", "siteb", ("home", "ops"), 290),
        _scene("hubitat-main", "siteb", ("home", "ops"), 285),
        _scene("goes16", "satellite", ("science",), 280),
        _scene("argonne", "highlights", ("science",), 275),
        _scene("noaa", "highlights", ("science",), 270),
        _scene("kenosha", "kenosha", ("regional", "scenic"), 265),
        _scene("cindys", "cindys", ("scenic",), 260),
        _scene("lincoln", "lincolnpark", ("beach", "scenic"), 255),
        _scene("grower", "plants", ("plants",), 250),
        _scene("sitea", "sitea", ("retail",), 245),
    ]
    hero_names = [
        "HubitatMotion",
        "HubitatPower",
        "HubitatControlPanel",
        "HubitatExterior",
        "HubitatSecurity",
        "HubitatNetwork",
        "HubitatMedia",
        "HubitatMain",
        "GOES16",
        "Argonne",
        "NOAA",
        "Kenosha",
        "CindysRooftopBean",
        "LincolnPark2800LakeShore",
        "WhiteGrowerOverhead",
        "SiteAEntryFisheye",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=16,
    )

    siteb_positions = [
        index for index, scene in enumerate(selected) if scene["group_name"] == "siteb"
    ]

    assert siteb_positions == [0, 2, 4, 6, 8, 10, 12, 14]


def test_hal_camera_minimums_keep_lake_corridor_views_when_available() -> None:
    scenes = [
        _scene("southport", "regional", ("kenosha", "harbor", "weather"), 320),
        _scene("northpoint", "regional", ("regional", "beach"), 315),
        _scene("waukegan", "regional", ("regional", "beach"), 310),
        _scene(
            "waukegan-weatherbug", "regional", ("waukegan", "harbor", "weather"), 305
        ),
    ]
    hero_names = [
        "SouthportMarinaKenosha",
        "NorthPointMarina",
        "WaukeganHarbor",
        "WaukeganHarborWeatherbug",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=4,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_hal_camera_minimums_keep_faa_when_available() -> None:
    scenes = [
        _scene("goes16", "satellite", ("scenic", "science", "world"), 320),
        _scene("argonne", "highlights", ("science",), 315),
        _scene("faa", "chicago", ("ops", "science", "scenic"), 310),
    ]
    hero_names = [
        "GOES16",
        "Argonne",
        "FAA",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=3,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_hal_camera_minimums_keep_buoy_and_garden_views_when_available() -> None:
    scenes = [
        _scene("winthrop", "winthrop", ("regional", "beach", "scenic"), 320),
        _scene("waukegan-buoy", "waukegan", ("regional", "beach", "scenic"), 315),
        _scene("titan-arum", "garden", ("scenic", "science"), 310),
        _scene("circle-garden", "garden", ("scenic",), 305),
        _scene("botany-pond", "garden", ("scenic", "science"), 300),
    ]
    hero_names = [
        "WinthropBuoy",
        "WaukeganBuoy",
        "TitanArumGarden",
        "CircleGardenLive",
        "BotanyPondUChicago",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=5,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_hal_camera_minimums_keep_beach_side_views_when_available() -> None:
    scenes = [
        _scene("northwestern", "beach", ("beach", "scenic"), 320),
        _scene("edgewater", "beach", ("beach", "scenic"), 315),
        _scene("ice-cover", "beach", ("beach", "science"), 310),
    ]
    hero_names = [
        "Northwestern",
        "Edgewater",
        "IceCover",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=3,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_hal_camera_minimums_keep_beachhouse_views_when_available() -> None:
    scenes = [
        _scene("beach-maple", "beachhouse", ("beach", "home", "regional"), 320),
        _scene("beach-front", "beachhouse", ("beach", "home", "regional"), 315),
        _scene("beach-shore", "beachhouse", ("beach", "home", "regional"), 310),
        _scene("beach-gravel", "beachhouse", ("beach", "home", "regional"), 305),
        _scene("beach-driveway", "beachhouse", ("beach", "home", "regional"), 300),
        _scene("beach-pathway", "beachhouse", ("beach", "home", "regional"), 295),
        _scene("beach-bioswale", "beachhouse", ("beach", "home", "regional"), 290),
        _scene("beach-north-jetty", "beachhouse", ("beach", "home", "regional"), 285),
    ]
    hero_names = [
        "BeachMapleTree",
        "BeachFrontYard",
        "BeachShore",
        "BeachGravel",
        "BeachDriveway",
        "BeachPathway",
        "BeachBioswale",
        "BeachNorthJetty",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=8,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_hal_camera_minimums_keep_chicago_expansion_views_when_available() -> None:
    scenes = [
        _scene("blue-island", "regional", ("regional", "scenic"), 320),
        _scene("cindys", "chicago", ("scenic", "science"), 315),
        _scene("lincoln-park", "chicago", ("beach", "scenic"), 310),
    ]
    hero_names = [
        "BlueIslandRailcam",
        "CindysRooftopBean",
        "LincolnPark2800LakeShore",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["hal"],
        max_scenes=4,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_camera_minimums_keep_hubitat_views_when_available() -> None:
    scenes = [
        _scene("hubitat-motion", "siteb", ("home", "ops"), 320),
        _scene("hubitat-power", "siteb", ("home", "ops"), 315),
        _scene("hubitat-control", "siteb", ("home", "ops"), 310),
        _scene("hubitat-exterior", "siteb", ("home", "ops"), 305),
        _scene("hubitat-security", "siteb", ("home", "ops"), 300),
    ]
    hero_names = [
        "HubitatMotion",
        "HubitatPower",
        "HubitatControlPanel",
        "HubitatExterior",
        "HubitatSecurity",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=5,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_distributes_siteb_scenes_through_rundown() -> None:
    scenes = [
        _scene("hubitat-motion", "siteb", ("home", "ops"), 320),
        _scene("hubitat-power", "siteb", ("home", "ops"), 315),
        _scene("hubitat-control", "siteb", ("home", "ops"), 310),
        _scene("hubitat-exterior", "siteb", ("home", "ops"), 305),
        _scene("hubitat-security", "siteb", ("home", "ops"), 300),
        _scene("hubitat-network", "siteb", ("home", "ops"), 295),
        _scene("hubitat-media", "siteb", ("home", "ops"), 290),
        _scene("hubitat-main", "siteb", ("home", "ops"), 285),
        _scene("goes16", "satellite", ("science",), 280),
        _scene("bandwidth", "network", ("ops",), 275),
        _scene("radiation", "emergency", ("ops", "science"), 270),
        _scene("waukegan", "waukegan", ("regional",), 265),
        _scene("botany", "garden", ("science",), 260),
    ]
    hero_names = [
        "HubitatMotion",
        "HubitatPower",
        "HubitatControlPanel",
        "HubitatExterior",
        "HubitatSecurity",
        "HubitatNetwork",
        "HubitatMedia",
        "HubitatMain",
        "GOES16",
        "BandwidthTX",
        "RadiationNetwork",
        "WaukeganBuoy",
        "BotanyPondUChicago",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=13,
    )

    siteb_positions = [
        index for index, scene in enumerate(selected) if scene["group_name"] == "siteb"
    ]

    assert siteb_positions != list(range(8))
    assert selected[0]["group_name"] == "siteb"
    assert any(scene["group_name"] != "siteb" for scene in selected[1:5])


def test_hal_siteb_scenes_get_extra_dwell_time() -> None:
    siteb_scene = _scene("HubitatMotion", "siteb", ("home", "ops"), 320)
    chicago_scene = _scene("River", "river", ("regional", "scenic"), 310)

    siteb_timed = _apply_scene_timing(
        siteb_scene,
        LANDING_MODE_PROFILES["ultra"],
        LANDING_CONTENT_PROFILES["hal"],
    )
    chicago_timed = _apply_scene_timing(
        chicago_scene,
        LANDING_MODE_PROFILES["ultra"],
        LANDING_CONTENT_PROFILES["hal"],
    )

    assert siteb_timed["rotation_ms"] > chicago_timed["rotation_ms"]


def test_office_siteb_scenes_get_extra_dwell_time() -> None:
    siteb_scene = _scene("HubitatMotion", "siteb", ("home", "ops"), 320)
    network_scene = _scene("BandwidthTX", "network", ("ops",), 310)

    siteb_timed = _apply_scene_timing(
        siteb_scene,
        LANDING_MODE_PROFILES["high"],
        LANDING_CONTENT_PROFILES["office"],
    )
    network_timed = _apply_scene_timing(
        network_scene,
        LANDING_MODE_PROFILES["high"],
        LANDING_CONTENT_PROFILES["office"],
    )

    assert siteb_timed["rotation_ms"] > network_timed["rotation_ms"]


def test_hal_beachhouse_scenes_get_extra_dwell_time() -> None:
    beachhouse_scene = _scene(
        "BeachShore",
        "beachhouse",
        ("beach", "home", "regional"),
        320,
    )
    beach_home_scene = _scene(
        "GenericBeachHome",
        "beach",
        ("beach", "home", "regional"),
        310,
    )

    beachhouse_timed = _apply_scene_timing(
        beachhouse_scene,
        LANDING_MODE_PROFILES["ultra"],
        LANDING_CONTENT_PROFILES["hal"],
    )
    beach_home_timed = _apply_scene_timing(
        beach_home_scene,
        LANDING_MODE_PROFILES["ultra"],
        LANDING_CONTENT_PROFILES["hal"],
    )

    assert beachhouse_timed["rotation_ms"] > beach_home_timed["rotation_ms"]


def test_office_camera_minimums_keep_lake_corridor_views_when_available() -> None:
    scenes = [
        _scene("northpoint", "regional", ("regional", "beach"), 320),
        _scene("waukegan", "regional", ("regional", "beach"), 315),
        _scene("southport", "regional", ("kenosha", "harbor", "weather"), 310),
    ]
    hero_names = [
        "NorthPointMarina",
        "WaukeganHarbor",
        "SouthportMarinaKenosha",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=3,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_camera_minimums_keep_waukegan_buoy_and_botany_when_available() -> None:
    scenes = [
        _scene("waukegan-buoy", "waukegan", ("regional", "beach", "scenic"), 320),
        _scene("botany-pond", "garden", ("scenic", "science"), 315),
    ]
    hero_names = [
        "WaukeganBuoy",
        "BotanyPondUChicago",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=2,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_camera_minimums_keep_faa_when_available() -> None:
    scenes = [
        _scene("hubitat-motion", "siteb", ("home", "ops"), 320),
        _scene("goes16", "satellite", ("scenic", "science", "world"), 315),
        _scene("faa", "chicago", ("ops", "science", "scenic"), 310),
    ]
    hero_names = [
        "HubitatMotion",
        "GOES16",
        "FAA",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=3,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_camera_minimums_keep_network_views_when_available() -> None:
    scenes = [
        _scene("hubitat-motion", "siteb", ("home", "ops"), 320),
        _scene("hubitat-power", "siteb", ("home", "ops"), 315),
        _scene("hubitat-control", "siteb", ("home", "ops"), 310),
        _scene("hubitat-exterior", "siteb", ("home", "ops"), 305),
        _scene("hubitat-security", "siteb", ("home", "ops"), 300),
        _scene("hubitat-network", "siteb", ("home", "ops"), 295),
        _scene("hubitat-media", "siteb", ("home", "ops"), 292),
        _scene("hubitat-main", "siteb", ("home", "ops"), 291),
        _scene("wifi", "network", ("ops", "science"), 290),
    ]
    hero_names = [
        "HubitatMotion",
        "HubitatPower",
        "HubitatControlPanel",
        "HubitatExterior",
        "HubitatSecurity",
        "HubitatNetwork",
        "HubitatMedia",
        "HubitatMain",
        "WiFi",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=9,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_camera_minimums_keep_beachhouse_views_when_available() -> None:
    scenes = [
        _scene("beach-maple", "beachhouse", ("beach", "home", "regional"), 330),
        _scene("beach-front", "beachhouse", ("beach", "home", "regional"), 325),
        _scene("beach-shore", "beachhouse", ("beach", "home", "regional"), 320),
        _scene("beach-driveway", "beachhouse", ("beach", "home", "regional"), 315),
        _scene("beach-pathway", "beachhouse", ("beach", "home", "regional"), 310),
        _scene("beach-north-jetty", "beachhouse", ("beach", "home", "regional"), 305),
    ]
    hero_names = [
        "BeachMapleTree",
        "BeachFrontYard",
        "BeachShore",
        "BeachDriveway",
        "BeachPathway",
        "BeachNorthJetty",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=6,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_camera_minimums_keep_science_views_when_available() -> None:
    scenes = [
        _scene("goes16", "satellite", ("scenic", "science", "world"), 320),
        _scene("noaa", "highlights", ("scenic", "science"), 315),
    ]
    hero_names = [
        "GOES16",
        "NOAA",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=2,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_office_composition_keeps_kenosha_and_sitec_when_available() -> None:
    scenes = [
        _scene("ops-1", "network", ("ops",), 320),
        _scene("home-1", "siteb", ("home",), 310),
        _scene("science-1", "satellite", ("science",), 300),
        _scene("kenosha-1", "kenosha", ("regional", "scenic"), 250),
        _scene("plants-1", "plants", ("plants",), 280),
        _scene("sitec-1", "sitec", ("retail",), 245),
        _scene("scenic-1", "sky", ("scenic",), 240),
    ]

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["office"],
        max_scenes=7,
    )

    selected_groups = {scene["group_name"] for scene in selected}

    assert "kenosha" in selected_groups
    assert "sitec" in selected_groups


def test_living_composition_keeps_beach_and_chicago_when_available() -> None:
    scenes = [
        _scene("scenic-1", "skyline", ("scenic",), 320),
        _scene("science-1", "satellite", ("science",), 310),
        _scene("beach-1", "beach", ("beach", "regional", "scenic"), 300),
        _scene("chicago-1", "chicago", ("scenic", "science"), 290),
        _scene("home-1", "siteb", ("home",), 280),
        _scene("regional-1", "sky", ("regional", "scenic", "science"), 270),
    ]

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["living"],
        max_scenes=6,
    )

    selected_groups = {scene["group_name"] for scene in selected}

    assert "beach" in selected_groups
    assert "chicago" in selected_groups
    assert "skyline" in selected_groups


def test_living_camera_minimums_keep_river_uic_and_goes_when_available() -> None:
    scenes = [
        _scene("river", "chicago", ("scenic", "science"), 320),
        _scene("uic", "skyline", ("scenic",), 315),
        _scene("goes16", "satellite", ("scenic", "science", "world"), 310),
    ]
    hero_names = [
        "River",
        "UICSkyline",
        "GOES16",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["living"],
        max_scenes=3,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_living_camera_minimums_keep_lake_corridor_views_when_available() -> None:
    scenes = [
        _scene("southport", "regional", ("kenosha", "harbor", "weather"), 320),
        _scene(
            "waukegan-weatherbug", "regional", ("waukegan", "harbor", "weather"), 315
        ),
    ]
    hero_names = [
        "SouthportMarinaKenosha",
        "WaukeganHarborWeatherbug",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["living"],
        max_scenes=2,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_living_chicago_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "chicago",
        [
            {"name": "River"},
            {"name": "CindysRooftopBean"},
            {"name": "LincolnPark2800LakeShore"},
        ],
        scene_size=4,
        content=views.LANDING_CONTENT_PROFILES["living"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_living_camera_minimums_keep_winthrop_and_botany_when_available() -> None:
    scenes = [
        _scene("winthrop", "winthrop", ("regional", "beach", "scenic"), 320),
        _scene("botany-pond", "garden", ("scenic", "science"), 315),
    ]
    hero_names = [
        "WinthropBuoy",
        "BotanyPondUChicago",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["living"],
        max_scenes=2,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_living_camera_minimums_keep_cindys_and_lincoln_park_when_available() -> None:
    scenes = [
        _scene("cindys", "chicago", ("scenic", "science"), 320),
        _scene("lincoln-park", "chicago", ("beach", "scenic"), 315),
    ]
    hero_names = [
        "CindysRooftopBean",
        "LincolnPark2800LakeShore",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["living"],
        max_scenes=2,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_living_camera_minimums_keep_river_cindys_and_lincoln_when_available() -> None:
    scenes = [
        _scene("river", "chicago", ("scenic", "science"), 320),
        _scene("cindys", "chicago", ("scenic", "science"), 315),
        _scene("lincoln-park", "chicago", ("beach", "scenic"), 310),
    ]
    hero_names = [
        "River",
        "CindysRooftopBean",
        "LincolnPark2800LakeShore",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["living"],
        max_scenes=3,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_kitchen_sitea_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "sitea",
        [
            {"name": "Safe_camera"},
            {"name": "Showroom_Entrance"},
            {"name": "SiteA1500"},
        ],
        scene_size=4,
        content=views.LANDING_CONTENT_PROFILES["kitchen"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1, 1]


def test_kitchen_garden_group_can_split_into_distinct_scene_windows() -> None:
    chunks = views._group_scene_chunks(
        "garden",
        [
            {"name": "CircleGardenLive"},
            {"name": "TitanArumGarden"},
        ],
        scene_size=4,
        content=views.LANDING_CONTENT_PROFILES["kitchen"],
    )

    assert [len(chunk) for chunk in chunks] == [1, 1]


def test_kitchen_composition_keeps_local_retail_and_beach_when_available() -> None:
    scenes = [
        _scene("sitea-1", "sitea", ("retail", "science"), 320),
        _scene("sitea-2", "sitea", ("home", "plants", "retail"), 315),
        _scene("sitec-1", "sitec", ("retail",), 310),
        _scene("beach-1", "beach", ("beach", "regional", "scenic"), 305),
        _scene("chicago-1", "chicago", ("scenic", "science"), 304),
        _scene("home-1", "siteb", ("home",), 300),
        _scene("scenic-1", "skyline", ("scenic",), 295),
    ]

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["kitchen"],
        max_scenes=7,
    )

    selected_groups = [scene["group_name"] for scene in selected]

    assert selected_groups.count("sitea") == 2
    assert "sitec" in selected_groups
    assert "beach" in selected_groups
    assert "chicago" in selected_groups
    assert "skyline" in selected_groups


def test_kitchen_camera_minimums_keep_sitea_showroom_river_and_uic_when_available() -> (
    None
):
    scenes = [
        _scene("showroom", "sitea", ("home", "plants", "retail"), 320),
        _scene("river", "chicago", ("scenic", "science"), 315),
        _scene("uic", "skyline", ("scenic",), 310),
    ]
    hero_names = [
        "SiteAShowroomWide",
        "River",
        "UICSkyline",
    ]
    for scene, hero_name in zip(scenes, hero_names, strict=True):
        scene["hero"]["name"] = hero_name

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["kitchen"],
        max_scenes=3,
    )

    assert {scene["hero"]["name"] for scene in selected} == set(hero_names)


def test_kitchen_camera_minimums_keep_lincoln_park_lakefront_when_available() -> None:
    scenes = [
        _scene("lincoln-park", "chicago", ("lincolnpark", "beach", "skyline"), 320),
    ]
    scenes[0]["hero"]["name"] = "LincolnPark2800LakeShore"

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["kitchen"],
        max_scenes=1,
    )

    assert {scene["hero"]["name"] for scene in selected} == {"LincolnPark2800LakeShore"}


def test_kitchen_camera_minimums_keep_circle_garden_when_available() -> None:
    scenes = [
        _scene("circle-garden", "garden", ("scenic",), 320),
    ]
    scenes[0]["hero"]["name"] = "CircleGardenLive"

    selected = _compose_profiled_scenes(
        scenes,
        LANDING_CONTENT_PROFILES["kitchen"],
        max_scenes=1,
    )

    assert {scene["hero"]["name"] for scene in selected} == {"CircleGardenLive"}


def test_build_landing_scenes_skips_private_cameras() -> None:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    templates = {
        "PublicSkyline": {
            "groups": "chicago,skyline",
            "last_screenshot_time": now,
            "capture_failed": 0,
            "private_camera": 0,
            "url": "https://example.test/public-skyline.jpg",
        },
        "DuplicateSkyline": {
            "groups": "chicago,skyline",
            "last_screenshot_time": now,
            "capture_failed": 0,
            "private_camera": 1,
            "url": "https://example.test/duplicate-skyline.jpg",
        },
    }

    scenes = _build_landing_scenes(
        templates,
        LANDING_MODE_PROFILES["medium"],
        LANDING_CONTENT_PROFILES["living"],
    )

    hero_names = {scene["hero"]["name"] for scene in scenes}

    assert "PublicSkyline" in hero_names
    assert "DuplicateSkyline" not in hero_names


def test_build_landing_events_returns_recent_motion_interrupts() -> None:
    scene = _scene("siteb-HubitatMotion", "siteb", ("home", "ops"), 320)
    scene["hero"]["name"] = "HubitatMotion"
    scene["hero"]["last_motion_time"] = "2999-01-01 00:00:00"
    scene["hero"]["last_video_time"] = "2999-01-01 00:00:00"

    events = _build_landing_events(
        [scene],
        LANDING_CONTENT_PROFILES["hal"],
    )

    assert len(events) == 1
    assert events[0]["scene_id"] == "siteb-HubitatMotion"
    assert events[0]["camera_name"] == "HubitatMotion"
    assert events[0]["level"] in {"alert", "significant"}


def test_build_landing_events_prefers_video_for_significant_motion() -> None:
    scene = _scene("siteb-HubitatExterior", "siteb", ("home", "ops"), 300)
    scene["hero"]["name"] = "HubitatExterior"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    scene["hero"]["last_motion_time"] = now
    scene["hero"]["last_screenshot_time"] = now
    scene["hero"]["priority_event"] = True
    scene["hero"]["last_video_time"] = now

    events = _build_landing_events(
        [scene],
        LANDING_CONTENT_PROFILES["office"],
    )

    assert len(events) == 1
    assert events[0]["prefer_video"] is True
