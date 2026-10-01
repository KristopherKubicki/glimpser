from __future__ import annotations

from scripts.refresh_template_notes import TemplateRow, build_refreshed_note


def _row(
    *,
    name: str = "Camera",
    groups: set[str] | None = None,
    url: str = "",
    notes: str = "",
    view_description: str = "",
    view_direction: str = "",
) -> TemplateRow:
    return TemplateRow(
        name=name,
        groups=groups or set(),
        url=url,
        notes=notes,
        view_description=view_description,
        view_direction=view_direction,
    )


def test_refresh_prefers_view_description_and_focus():
    note = build_refreshed_note(
        _row(
            name="Backyard",
            groups={"private", "sky"},
            notes="This fish-eye wall camera has a rotated view.",
            view_description="Backyard dewarped view across the yard and sky.",
            view_direction="W/WNW",
        )
    )

    assert "Backyard dewarped view across the yard and sky" in note
    assert "Direction: W/WNW" in note
    assert "people, vehicles, packages" in note
    assert "Ignore embedded timestamps" in note


def test_refresh_keeps_source_caveat_but_removes_churn_history():
    note = build_refreshed_note(
        _row(
            name="River",
            groups={"chicago", "river"},
            notes=(
                "This is a live camera capture of the Chicago River.\n"
                "Eyebat 2026-05-03: Wetmet widget uses extracted signed HLS stream."
            ),
            url="https://api.wetmet.net/widgets/stream/frame.php",
        )
    )

    assert "Wetmet" not in note
    assert "Browser/HLS source can be heavy" in note
    assert "Eyebat 2026-05-03" not in note


def test_refresh_adds_archive_and_solar_guidance():
    archived = build_refreshed_note(
        _row(
            name="OldCam",
            groups={"archive", "source-stale"},
            notes="Demoted 2026-05-02 by Eyebat rotation hygiene.",
        )
    )
    solar = build_refreshed_note(
        _row(
            name="BeachShore",
            groups={"beachhouse", "eufy"},
            url="eufy://macmini/shore",
            notes="Eufy Mac mini screenshot bridge.",
        )
    )

    assert "Source state: archived or stale" in archived
    assert "Solar Eufy cameras may show a last-good frame" in solar
    assert "lake level, waves, shore condition" in solar


def test_refresh_infers_focus_when_groups_are_sparse():
    ais = build_refreshed_note(
        _row(
            name="AIS",
            url="https://www.myshiptracking.com/",
            notes="This map tracks maritime traffic. Any big ships?",
        )
    )
    traffic = build_refreshed_note(
        _row(
            name="Argonne",
            notes="This is a live traffic camera just outside Argonne.",
        )
    )

    assert "vessel traffic, named ships" in ais
    assert "road speed, backups" in traffic


def test_refresh_is_idempotent_and_avoids_bad_inference():
    first = build_refreshed_note(
        _row(
            name="BeachShore",
            groups={"beachhouse", "eufy"},
            url="eufy://macmini/shore",
            notes="Eufy Mac mini screenshot bridge. Solar cameras may show last-good images.",
            view_description="Lake Michigan shore view.",
        )
    )
    second = build_refreshed_note(
        _row(
            name="BeachShore",
            groups={"beachhouse", "eufy"},
            url="eufy://macmini/shore",
            notes=first,
            view_description="Lake Michigan shore view.",
        )
    )
    grower = build_refreshed_note(
        _row(
            name="WhiteGrowerOverheadROICenter",
            groups={"plants", "grower"},
            notes="Focus on plant health and leaf posture.",
        )
    )

    assert first == second
    assert "space-weather activity" not in first
    assert "plant health, color" in grower
    assert "regional health status" not in grower


def test_refresh_cloudping_is_network_not_weather():
    note = build_refreshed_note(
        _row(
            name="Cloudping",
            groups={"network"},
            notes="This is our local ping time to Amazon data centers. Ohio should be under 100ms.",
        )
    )

    assert "AWS CloudPing latency dashboard" in note
    assert "us-east-2/Ohio" in note
    assert "cloud structure" not in note


def test_generated_subjects_do_not_assign_installation_locations():
    for group, expected in (
        ("eufy", "Eufy camera"),
        ("retail", "Retail camera"),
        ("private", "Private site camera"),
        ("marine", "Marine view"),
    ):
        note = build_refreshed_note(_row(name="Example", groups={group}))
        assert expected in note
