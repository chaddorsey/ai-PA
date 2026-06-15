"""OmniFocus sidebar tree normalization.

Root cause (2026-06-15): the sidebar showed all 80 projects (39 active + 41 done)
because _normalize_of_tree never filtered completed projects, and kept folders that
held only completed projects. The bridge exposes a per-project `completed` flag.

Expected: completed projects excluded; folders left with nothing live are pruned.

Run: cd pa-web-ui && python -m pytest tests/test_omnifocus_tree.py -v
"""
import app


def _names(nodes, typ):
    out = []
    for n in nodes:
        if n["type"] == typ:
            out.append(n["name"])
        out += _names(n["children"], typ)
    return out


SUBFOLDERS = [
    {
        "folder": {"id": "f1", "name": "Active Folder"},
        "subfolders": [],
        "projects": [
            {"id": "p1", "name": "Live Project", "completed": False},
            {"id": "p2", "name": "Done Project", "completed": True},
        ],
    },
    {
        "folder": {"id": "f2", "name": "Archive"},
        "subfolders": [],
        "projects": [{"id": "p3", "name": "Old Done", "completed": True}],
    },
    {
        "folder": {"id": "f3", "name": "Parent"},
        "subfolders": [
            {"folder": {"id": "f4", "name": "Sub Active"}, "subfolders": [],
             "projects": [{"id": "p4", "name": "Sub Live", "completed": False}]},
            {"folder": {"id": "f5", "name": "Sub Dead"}, "subfolders": [],
             "projects": [{"id": "p5", "name": "Sub Done", "completed": True}]},
        ],
        "projects": [],
    },
]


def test_excludes_completed_projects():
    projects = _names(app._normalize_of_tree(SUBFOLDERS), "project")
    assert "Live Project" in projects
    assert "Sub Live" in projects
    assert "Done Project" not in projects
    assert "Old Done" not in projects
    assert "Sub Done" not in projects


def test_prunes_folders_left_empty():
    folders = _names(app._normalize_of_tree(SUBFOLDERS), "folder")
    assert "Active Folder" in folders     # has a live project
    assert "Sub Active" in folders        # has a live project
    assert "Parent" in folders            # kept: contains a live subfolder
    assert "Archive" not in folders       # only completed projects -> pruned
    assert "Sub Dead" not in folders      # only completed projects -> pruned
