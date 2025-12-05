#!/usr/bin/env python3
"""
Test script to verify the orchestrate_scheduling tool works with Letta-style input.
Converts event data format and calls the tool directly.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "letta"))

from scheduling_orchestrator.orchestrate_scheduling import orchestrate_scheduling

# Convert event format from Letta's nested structure to tool's expected format
def convert_event_format(event):
    """Convert event from Letta format (nested dateTime) to tool format (flat ISO strings)."""
    converted = {}
    # Copy all fields
    for key, value in event.items():
        if key == 'start' and isinstance(value, dict):
            # Extract dateTime from nested start object
            converted['start'] = value.get('dateTime', str(value))
        elif key == 'end' and isinstance(value, dict):
            # Extract dateTime from nested end object
            converted['end'] = value.get('dateTime', str(value))
        elif key == 'summary':
            # Map summary to title
            converted['title'] = value
            converted['summary'] = value  # Keep both for compatibility
        else:
            converted[key] = value
    return converted

# Leslie's events (full list from user)
leslie_events_raw = [
  {"summary": "Fill in Timesheet", "id": "4tp9pkhku7fpg4qv7nfl2n8jv0_20251212T130000Z", "start": {"dateTime": "2025-12-12T08:00:00-05:00"}, "end": {"dateTime": "2025-12-12T09:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Fill in Timesheet", "id": "4tp9pkhku7fpg4qv7nfl2n8jv0_20251219T130000Z", "start": {"dateTime": "2025-12-19T08:00:00-05:00"}, "end": {"dateTime": "2025-12-19T09:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad & Leslie", "id": "5o5poen7um7fgn5od9bvfhn5ak_20251215T171500Z", "start": {"dateTime": "2025-12-15T11:15:00-05:00"}, "end": {"dateTime": "2025-12-15T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "MODS Research and Tech meeting", "id": "_60q30c1g60o30e1i60o4ac1g60rj8gpl88rj2c1h84s34h9g60s30c1g60o30c1g6d1k4dhm64pk2gi164qk8gpg64o30c1g60o30c1g60o30c1g60o32c1g60o30c1g6l2k6cq168p4cc1k6cq36e1k74sk4gph68q3gga38or36c9h6ssg_20251209T140000Z", "start": {"dateTime": "2025-12-09T09:00:00-05:00"}, "end": {"dateTime": "2025-12-09T10:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 9, "internal_only": False},
  {"summary": "MODS Research and Tech meeting", "id": "_60q30c1g60o30e1i60o4ac1g60rj8gpl88rj2c1h84s34h9g60s30c1g60o30c1g6d1k4dhm64pk2gi164qk8gpg64o30c1g60o30c1g60o30c1g60o32c1g60o30c1g6l2k6cq168p4cc1k6cq36e1k74sk4gph68q3gga38or36c9h6ssg_20251216T140000Z", "start": {"dateTime": "2025-12-16T09:00:00-05:00"}, "end": {"dateTime": "2025-12-16T10:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 9, "internal_only": False},
  {"summary": "Mindfulness Wednesday", "id": "06uocscc5se35n9o3ludv46d21_20251217T210000Z", "start": {"dateTime": "2025-12-17T16:00:00-05:00"}, "end": {"dateTime": "2025-12-17T16:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 26, "internal_only": True},
  {"summary": "Leslie Out", "id": "pm0isatn4f5lka22l0upjtdq8s_20251212T170000Z", "start": {"dateTime": "2025-12-12T12:00:00-05:00"}, "end": {"dateTime": "2025-12-12T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": False},
  {"summary": "Leslie Out", "id": "pm0isatn4f5lka22l0upjtdq8s_20251219T170000Z", "start": {"dateTime": "2025-12-19T12:00:00-05:00"}, "end": {"dateTime": "2025-12-19T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": False},
  {"summary": "All Dev Standup", "id": "12lsn1l3psa3rcj4f27hi2327o_20251208T173000Z", "start": {"dateTime": "2025-12-08T12:30:00-05:00"}, "end": {"dateTime": "2025-12-08T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 11, "internal_only": False},
  {"summary": "All Dev Standup", "id": "12lsn1l3psa3rcj4f27hi2327o_20251215T173000Z", "start": {"dateTime": "2025-12-15T12:30:00-05:00"}, "end": {"dateTime": "2025-12-15T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 11, "internal_only": False},
  {"summary": "Inquisitive & Concord Consortium", "id": "1ddsme8fdl8kgkmt3ua7k9dbmk", "start": {"dateTime": "2025-12-09T12:00:00-05:00"}, "end": {"dateTime": "2025-12-09T12:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Teale and Leslie Checkin", "id": "4i3v1nb3jg1f9nkva3e4bdgqf5_20251209T210000Z", "start": {"dateTime": "2025-12-09T16:00:00-05:00"}, "end": {"dateTime": "2025-12-09T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Teale and Leslie Checkin", "id": "4i3v1nb3jg1f9nkva3e4bdgqf5_20251216T210000Z", "start": {"dateTime": "2025-12-16T16:00:00-05:00"}, "end": {"dateTime": "2025-12-16T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Send invoice to BC", "id": "694geg0ctpm12a7u3508vlmded", "start": {"dateTime": "2025-12-19T08:30:00-05:00"}, "end": {"dateTime": "2025-12-19T08:55:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Dev Team Grooming", "id": "rht8potadg74tlskri6qcrq9in_20251216T180000Z", "start": {"dateTime": "2025-12-16T13:00:00-05:00"}, "end": {"dateTime": "2025-12-16T13:40:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 10, "internal_only": False},
  {"summary": "Leslie / Kiley 1:1", "id": "992lfo8aj4ooep1h7uvi2dc6oi_20251209T163000Z", "start": {"dateTime": "2025-12-09T11:30:00-05:00"}, "end": {"dateTime": "2025-12-09T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Leslie / Kiley 1:1", "id": "992lfo8aj4ooep1h7uvi2dc6oi_20251216T163000Z", "start": {"dateTime": "2025-12-16T11:30:00-05:00"}, "end": {"dateTime": "2025-12-16T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "MSU/Concord Zoom Meeting", "id": "kr4efemkhka5qc4ccphj6917n2_20251210T160000Z", "start": {"dateTime": "2025-12-10T11:00:00-05:00"}, "end": {"dateTime": "2025-12-10T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 17, "internal_only": False},
  {"summary": "MSU/Concord Zoom Meeting", "id": "kr4efemkhka5qc4ccphj6917n2_20251217T160000Z", "start": {"dateTime": "2025-12-17T11:00:00-05:00"}, "end": {"dateTime": "2025-12-17T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 17, "internal_only": False},
  {"summary": "Leslie / Ethan", "id": "ils2v4fk69cka6523c671l1og3_20251210T190000Z", "start": {"dateTime": "2025-12-10T14:00:00-05:00"}, "end": {"dateTime": "2025-12-10T14:25:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Scott and Leslie check-in", "id": "bahchtou3anfkj34qim5j7krc7_20251211T150000Z", "start": {"dateTime": "2025-12-11T10:00:00-05:00"}, "end": {"dateTime": "2025-12-11T10:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Scott and Leslie check-in", "id": "bahchtou3anfkj34qim5j7krc7_20251218T150000Z", "start": {"dateTime": "2025-12-18T10:00:00-05:00"}, "end": {"dateTime": "2025-12-18T10:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "CODAP V3 Planning", "id": "7rhjeudbecodjdest60saaijnt", "start": {"dateTime": "2025-12-10T13:00:00-05:00"}, "end": {"dateTime": "2025-12-10T14:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 4, "internal_only": True},
  {"summary": "CODAP V3 Planning", "id": "2s91overc1o39lqa5ru7gbk8e6", "start": {"dateTime": "2025-12-16T12:00:00-05:00"}, "end": {"dateTime": "2025-12-16T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 4, "internal_only": True},
  {"summary": "Weekly Scrum", "id": "f09vfgk1tqe8sgb8761h8nroa5_20251208T151500Z", "start": {"dateTime": "2025-12-08T10:15:00-05:00"}, "end": {"dateTime": "2025-12-08T11:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Weekly Scrum", "id": "f09vfgk1tqe8sgb8761h8nroa5_20251215T151500Z", "start": {"dateTime": "2025-12-15T10:15:00-05:00"}, "end": {"dateTime": "2025-12-15T11:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "2025 End of Year Potluck 🥧", "id": "6dbh8cejuu2u4ofh5uhe3ief27", "start": {"dateTime": "2025-12-11T12:15:00-05:00"}, "end": {"dateTime": "2025-12-11T13:15:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Bug Triage 🐞", "id": "5fi71siucv7vg7u0qml7h2qu7r_20251208T183000Z", "start": {"dateTime": "2025-12-08T13:30:00-05:00"}, "end": {"dateTime": "2025-12-08T13:55:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Bug Triage 🐞", "id": "5fi71siucv7vg7u0qml7h2qu7r_20251215T183000Z", "start": {"dateTime": "2025-12-15T13:30:00-05:00"}, "end": {"dateTime": "2025-12-15T13:55:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "SeismicML T2 Dev", "id": "7e99vt6r1l1r99nk48mnobeg5a", "start": {"dateTime": "2025-12-16T10:00:00-05:00"}, "end": {"dateTime": "2025-12-16T10:50:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 7, "internal_only": True},
  {"summary": "Sprint 6 Plan & Groom", "id": "4u4mqph9r58u2ubi7dcsufp76l_20251209T180000Z", "start": {"dateTime": "2025-12-09T13:00:00-05:00"}, "end": {"dateTime": "2025-12-09T15:50:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 11, "internal_only": True},
  {"summary": "FlowAI & Brainwaves 2 T2 Dev", "id": "4kabupiki778gpbaj14ut0vr8c", "start": {"dateTime": "2025-12-17T13:00:00-05:00"}, "end": {"dateTime": "2025-12-17T13:50:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Mapping Time & LEADS T2 Dev", "id": "3q0ibm94tdmcfaecctn8i2gihq", "start": {"dateTime": "2025-12-12T11:30:00-05:00"}, "end": {"dateTime": "2025-12-12T12:20:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 6, "internal_only": True},
  {"summary": "Monthly Tech Demo/Infrastructure/AI Huddle", "id": "4hr04trt5jq3sp050cpl0cv0bg_20251217T190000Z", "start": {"dateTime": "2025-12-17T14:00:00-05:00"}, "end": {"dateTime": "2025-12-17T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 25, "internal_only": True},
  {"summary": "All-hands meeting", "id": "3rshjlft6106jri54rv2rb34a0_20251211T181500Z", "start": {"dateTime": "2025-12-11T13:15:00-05:00"}, "end": {"dateTime": "2025-12-11T14:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 28, "internal_only": False},
  {"summary": "Computational Thinking Rubric Design", "id": "13rn14032hd3dah81uil1km6f7_20251211T203000Z", "start": {"dateTime": "2025-12-11T15:30:00-05:00"}, "end": {"dateTime": "2025-12-11T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": False},
  {"summary": "FlowAI Grant Planning", "id": "1de220s3fmvgf9eabhk2mkqr17_20251211T163000Z", "start": {"dateTime": "2025-12-11T11:30:00-05:00"}, "end": {"dateTime": "2025-12-11T12:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "FlowAI Grant Planning", "id": "1de220s3fmvgf9eabhk2mkqr17_20251218T163000Z", "start": {"dateTime": "2025-12-18T11:30:00-05:00"}, "end": {"dateTime": "2025-12-18T12:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Computational Thinking Rubric Design", "id": "13rn14032hd3dah81uil1km6f7_20251218T203000Z", "start": {"dateTime": "2025-12-18T15:30:00-05:00"}, "end": {"dateTime": "2025-12-18T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": False},
  {"summary": "CT & AI Grant Meeting", "id": "00dlivgo3vnm9qijumkgrf1j2d_20251218T180000Z", "start": {"dateTime": "2025-12-18T13:00:00-05:00"}, "end": {"dateTime": "2025-12-18T14:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 7, "internal_only": False},
  {"summary": "PI / Supervisors: Review and approve timesheets", "id": "6v14tqha3mel4mhokbqtse61mo_20251217T213000Z", "start": {"dateTime": "2025-12-17T16:30:00-05:00"}, "end": {"dateTime": "2025-12-17T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 7, "internal_only": True},
  {"summary": "Leslie / Doug 1:1", "id": "6e0re7961e5trtgd12368u5324_20251211T143000Z", "start": {"dateTime": "2025-12-11T09:30:00-05:00"}, "end": {"dateTime": "2025-12-11T10:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Leslie / Doug 1:1", "id": "6e0re7961e5trtgd12368u5324_20251218T143000Z", "start": {"dateTime": "2025-12-18T09:30:00-05:00"}, "end": {"dateTime": "2025-12-18T10:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Concord Tech Capabilities Development Discussion", "id": "0f2t1rjk3mnti5acqt9gdclrn8_20251211T170000Z", "start": {"dateTime": "2025-12-11T12:00:00-05:00"}, "end": {"dateTime": "2025-12-11T13:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Concord Tech Capabilities Development Discussion", "id": "0f2t1rjk3mnti5acqt9gdclrn8_20251218T170000Z", "start": {"dateTime": "2025-12-18T12:00:00-05:00"}, "end": {"dateTime": "2025-12-18T13:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 5, "internal_only": True},
  {"summary": "AI Design Thinking", "id": "rngm55t9hebrf99npg0oqjo65c_20251210T170000Z", "start": {"dateTime": "2025-12-10T12:00:00-05:00"}, "end": {"dateTime": "2025-12-10T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 6, "internal_only": False},
  {"summary": "AI Design Thinking", "id": "rngm55t9hebrf99npg0oqjo65c_20251217T170000Z", "start": {"dateTime": "2025-12-17T12:00:00-05:00"}, "end": {"dateTime": "2025-12-17T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 6, "internal_only": False},
  {"summary": "APLUS T2 Dev", "id": "56vsqamn0sspjuh7hbihtc8a4f", "start": {"dateTime": "2025-12-16T15:00:00-05:00"}, "end": {"dateTime": "2025-12-16T16:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 8, "internal_only": True},
  {"summary": "Core Support ", "id": "4l4qsnaufsnuiar18579m71jju", "start": {"dateTime": "2025-12-15T15:30:00-05:00"}, "end": {"dateTime": "2025-12-15T16:15:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Meet n Chat", "id": "2s5a9tjb3ookncm9i4gqg1bfqp_20251211T210000Z", "start": {"dateTime": "2025-12-11T16:00:00-05:00"}, "end": {"dateTime": "2025-12-11T16:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Meet n Chat", "id": "2s5a9tjb3ookncm9i4gqg1bfqp_20251218T210000Z", "start": {"dateTime": "2025-12-18T16:00:00-05:00"}, "end": {"dateTime": "2025-12-18T16:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Chad & Leslie", "id": "0j0m3qej5nt75f6hn5elu7rmk8_20251208T190000Z", "start": {"dateTime": "2025-12-08T13:00:00-05:00"}, "end": {"dateTime": "2025-12-08T13:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True}
]

# Chad's events (full list from user)
chad_events_raw = [
  {"summary": "Chad/Hee-Sun", "id": "8h5d9mr8v30th3e7quftpb67c9_20251217T201500Z", "start": {"dateTime": "2025-12-17T15:15:00-05:00"}, "end": {"dateTime": "2025-12-17T16:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Project Budget Review (359, 372, 378, 381)", "id": "4rl1timvo6ogngunvm08um3qa2", "start": {"dateTime": "2025-12-15T14:00:00-05:00"}, "end": {"dateTime": "2025-12-15T14:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Chad & Leslie", "id": "5o5poen7um7fgn5od9bvfhn5ak_20251215T171500Z", "start": {"dateTime": "2025-12-15T11:15:00-05:00"}, "end": {"dateTime": "2025-12-15T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Chad/Bill", "id": "0qsq4pnd6umn128dqh2vks78lf_20251217T210000Z", "start": {"dateTime": "2025-12-17T16:00:00-05:00"}, "end": {"dateTime": "2025-12-17T16:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Hold", "id": "7qi0te4saehpkqo9e5uq06e0tp_20251209T160000Z", "start": {"dateTime": "2025-12-09T11:00:00-05:00"}, "end": {"dateTime": "2025-12-09T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Hold", "id": "7qi0te4saehpkqo9e5uq06e0tp_20251216T160000Z", "start": {"dateTime": "2025-12-16T11:00:00-05:00"}, "end": {"dateTime": "2025-12-16T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Hold Helen", "id": "7os8skq9jcj4an3i7gmtaieki6", "start": {"dateTime": "2025-12-11T16:00:00-05:00"}, "end": {"dateTime": "2025-12-11T16:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Hold Helen", "id": "1cf12c5prbp6jgsb9b6petk9ng", "start": {"dateTime": "2025-12-18T16:00:00-05:00"}, "end": {"dateTime": "2025-12-18T16:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Hold", "id": "082crer4gdmhqmsctdpd9o7d3t_20251210T190000Z", "start": {"dateTime": "2025-12-10T14:00:00-05:00"}, "end": {"dateTime": "2025-12-10T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Hold", "id": "082crer4gdmhqmsctdpd9o7d3t_20251217T190000Z", "start": {"dateTime": "2025-12-17T11:00:00-05:00"}, "end": {"dateTime": "2025-12-17T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Susan / Chad", "id": "4c0qj4br5plcs03srqknbb2n0r", "start": {"dateTime": "2025-12-18T13:00:00-05:00"}, "end": {"dateTime": "2025-12-18T13:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Chad/Dan", "id": "8vi2ib0bdcu5m02d9b3o2c1djs_20251214T210000Z", "start": {"dateTime": "2025-12-16T14:00:00-05:00"}, "end": {"dateTime": "2025-12-16T14:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Hold", "id": "1dkcv7q4bb7jo1h615t0carno1_20251212T170000Z", "start": {"dateTime": "2025-12-12T12:00:00-05:00"}, "end": {"dateTime": "2025-12-12T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Hold", "id": "1dkcv7q4bb7jo1h615t0carno1_20251219T170000Z", "start": {"dateTime": "2025-12-19T12:00:00-05:00"}, "end": {"dateTime": "2025-12-19T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chalk and Code podcast recording", "id": "9konpf6qmu6b0fedkcjh5qtmb8", "start": {"dateTime": "2025-12-12T13:00:00-05:00"}, "end": {"dateTime": "2025-12-12T14:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Letta office hours", "id": "078nus2iv2ihu3pn7khqg5dchr_20251211T193000Z", "start": {"dateTime": "2025-12-11T14:30:00-05:00"}, "end": {"dateTime": "2025-12-11T15:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Letta office hours", "id": "078nus2iv2ihu3pn7khqg5dchr_20251218T193000Z", "start": {"dateTime": "2025-12-18T14:30:00-05:00"}, "end": {"dateTime": "2025-12-18T15:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Concord Finance / AAFCPA Meeting", "id": "0l29rdqececsooads4mudb9lgq", "start": {"dateTime": "2025-12-12T12:00:00-05:00"}, "end": {"dateTime": "2025-12-12T12:50:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 8, "internal_only": False},
  {"summary": "Concord Consortium/Hewlett", "id": "27gb3ipaj27uuvrm1akkloaq00", "start": {"dateTime": "2025-12-10T14:00:00-05:00"}, "end": {"dateTime": "2025-12-10T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Inquisitive & Concord Consortium", "id": "1ddsme8fdl8kgkmt3ua7k9dbmk", "start": {"dateTime": "2025-12-09T12:00:00-05:00"}, "end": {"dateTime": "2025-12-09T12:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Chad/Sue Financial Review", "id": "48mm3rasbescrqfi8ufjbat9ei_20251219T193000Z", "start": {"dateTime": "2025-12-19T14:30:00-05:00"}, "end": {"dateTime": "2025-12-19T15:15:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Weekly Review", "id": "tu5qb09h8noohvl51ctvkjunaa_20251212T203000Z", "start": {"dateTime": "2025-12-12T15:30:00-05:00"}, "end": {"dateTime": "2025-12-12T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Weekly Review", "id": "tu5qb09h8noohvl51ctvkjunaa_20251219T203000Z", "start": {"dateTime": "2025-12-19T15:30:00-05:00"}, "end": {"dateTime": "2025-12-19T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad/Jie", "id": "cn1q8k0avbviv8chhs75ecan1o_20251217T200000Z", "start": {"dateTime": "2025-12-17T15:00:00-05:00"}, "end": {"dateTime": "2025-12-17T15:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Concord Consortium/Amgen", "id": "9e1eiphr86qnjd9ap44vifgkvc", "start": {"dateTime": "2025-12-10T12:00:00-05:00"}, "end": {"dateTime": "2025-12-10T12:40:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Concord Consortium/Sarah Dunton", "id": "0u62af1g41q5eu9d4vp5qu83vt", "start": {"dateTime": "2025-12-18T14:00:00-05:00"}, "end": {"dateTime": "2025-12-18T14:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Chad/Paul", "id": "479qiof9eq3hl5q6f1kmuhml2r_20251222T190000Z", "start": {"dateTime": "2025-12-15T12:00:00-05:00"}, "end": {"dateTime": "2025-12-15T12:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Chad/Amy", "id": "2g6d26e7cfvkt4l0a8vou4a3rk_20251223T190000Z", "start": {"dateTime": "2025-12-16T16:15:00-05:00"}, "end": {"dateTime": "2025-12-16T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Chad Dorsey and Theron Davis + 2 others", "id": "ibq4p3al2r5k0u36e0k5tmq7k8", "start": {"dateTime": "2025-12-19T13:00:00-05:00"}, "end": {"dateTime": "2025-12-19T14:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 4, "internal_only": False},
  {"summary": "Chad Dorsey, You're Booked for the AI CEO Roundtable (December 10, 2025 @ 3PM ET) ", "id": "_60q30c1g60o30e1i60o4ac1g60rj8gpl88rj2c1h84s34h9g60s30c1g60o30c1g692jad2474s32c1j6l348gpg64o30c1g60o30c1g60o30c1g60o32c1g60o30c1g64pjichl88oj2gpg74rjegpk850j0e9p84q3ad9g84ojge9n6l0g", "start": {"dateTime": "2025-12-10T15:00:00-05:00"}, "end": {"dateTime": "2025-12-10T16:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": False},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251208T140000Z", "start": {"dateTime": "2025-12-08T09:00:00-05:00"}, "end": {"dateTime": "2025-12-08T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251209T140000Z", "start": {"dateTime": "2025-12-09T09:00:00-05:00"}, "end": {"dateTime": "2025-12-09T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251210T140000Z", "start": {"dateTime": "2025-12-10T09:00:00-05:00"}, "end": {"dateTime": "2025-12-10T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251211T140000Z", "start": {"dateTime": "2025-12-11T09:00:00-05:00"}, "end": {"dateTime": "2025-12-11T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251212T140000Z", "start": {"dateTime": "2025-12-12T09:00:00-05:00"}, "end": {"dateTime": "2025-12-12T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251215T140000Z", "start": {"dateTime": "2025-12-15T09:00:00-05:00"}, "end": {"dateTime": "2025-12-15T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251216T140000Z", "start": {"dateTime": "2025-12-16T09:00:00-05:00"}, "end": {"dateTime": "2025-12-16T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251217T140000Z", "start": {"dateTime": "2025-12-17T09:00:00-05:00"}, "end": {"dateTime": "2025-12-17T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251218T140000Z", "start": {"dateTime": "2025-12-18T09:00:00-05:00"}, "end": {"dateTime": "2025-12-18T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Email & Tasks", "id": "o9jl388gbota6f74dvg1i0t0pj_20251219T140000Z", "start": {"dateTime": "2025-12-19T09:00:00-05:00"}, "end": {"dateTime": "2025-12-19T11:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Hold for potential Mapping Time kickoff for realz??", "id": "6i8lj7k5hevrdc4e1vtji85ju7", "start": {"dateTime": "2025-12-16T16:00:00-05:00"}, "end": {"dateTime": "2025-12-16T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "2025 End of Year Potluck 🥧", "id": "6dbh8cejuu2u4ofh5uhe3ief27", "start": {"dateTime": "2025-12-11T12:15:00-05:00"}, "end": {"dateTime": "2025-12-11T13:15:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Chad/Sue", "id": "48mm3rasbescrqfi8ufjbat9ei_20251212T193000Z", "start": {"dateTime": "2025-12-11T14:00:00-05:00"}, "end": {"dateTime": "2025-12-11T14:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "HOLD: Mapping Time RITEL Grant Launch", "id": "5q9hadfalat95gm79gi8idhbl6", "start": {"dateTime": "2025-12-16T16:00:00-05:00"}, "end": {"dateTime": "2025-12-16T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Troop Meeting", "id": "7oh5mlhbo9nujb47clplc2j584_20251211T000000Z", "start": {"dateTime": "2025-12-10T19:00:00-05:00"}, "end": {"dateTime": "2025-12-10T20:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 1, "internal_only": True},
  {"summary": "Troop Meeting", "id": "7oh5mlhbo9nujb47clplc2j584_20251218T000000Z", "start": {"dateTime": "2025-12-17T19:00:00-05:00"}, "end": {"dateTime": "2025-12-17T20:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 1, "internal_only": True},
  {"summary": "Strategy 2.0", "id": "3585665i0gfq1nn04plglisefd_20251216T160000Z", "start": {"dateTime": "2025-12-16T11:00:00-05:00"}, "end": {"dateTime": "2025-12-16T11:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Chad/Sue/Kathy", "id": "2qm0753ui3njdtbfbac2sh3r8q_20251218T180000Z", "start": {"dateTime": "2025-12-18T13:00:00-05:00"}, "end": {"dateTime": "2025-12-18T13:25:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Mapping Time & LEADS T2 Dev", "id": "3q0ibm94tdmcfaecctn8i2gihq", "start": {"dateTime": "2025-12-12T11:30:00-05:00"}, "end": {"dateTime": "2025-12-12T12:20:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 6, "internal_only": True},
  {"summary": "Monthly Tech Demo/Infrastructure/AI Huddle", "id": "4hr04trt5jq3sp050cpl0cv0bg_20251217T190000Z", "start": {"dateTime": "2025-12-17T14:00:00-05:00"}, "end": {"dateTime": "2025-12-17T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 25, "internal_only": True},
  {"summary": "Cynthia / Chad", "id": "n47opvl04tbkhtve8b1ujkabih_20251216T210000Z", "start": {"dateTime": "2025-12-15T16:15:00-05:00"}, "end": {"dateTime": "2025-12-15T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "All-hands meeting", "id": "3rshjlft6106jri54rv2rb34a0_20251211T181500Z", "start": {"dateTime": "2025-12-11T13:15:00-05:00"}, "end": {"dateTime": "2025-12-11T14:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 28, "internal_only": False},
  {"summary": "Concord Audit Drafts", "id": "7eedqhdpknl6q2nmauic8pfgf3", "start": {"dateTime": "2025-12-08T16:00:00-05:00"}, "end": {"dateTime": "2025-12-08T16:50:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": False},
  {"summary": "Development Weekly Check In", "id": "5lo4ai8kqfda9oaq2nu10iurlt_20251208T160000Z", "start": {"dateTime": "2025-12-08T11:00:00-05:00"}, "end": {"dateTime": "2025-12-08T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Development Weekly Check In", "id": "5lo4ai8kqfda9oaq2nu10iurlt_20251215T160000Z", "start": {"dateTime": "2025-12-15T11:00:00-05:00"}, "end": {"dateTime": "2025-12-15T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Judi / Chad", "id": "tukmo351hvp0cgksh3dubgubjn_20251210T190000Z", "start": {"dateTime": "2025-12-10T14:00:00-05:00"}, "end": {"dateTime": "2025-12-10T14:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Judi / Chad", "id": "tukmo351hvp0cgksh3dubgubjn_20251217T190000Z", "start": {"dateTime": "2025-12-17T14:00:00-05:00"}, "end": {"dateTime": "2025-12-17T14:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "PI / Supervisors: Review and approve timesheets", "id": "6v14tqha3mel4mhokbqtse61mo_20251217T213000Z", "start": {"dateTime": "2025-12-17T16:30:00-05:00"}, "end": {"dateTime": "2025-12-17T17:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 7, "internal_only": True},
  {"summary": "Concord Consortium/ Nancy - Gates Foundation", "id": "7r3549f2nbsiip9ddcuu66b8vd", "start": {"dateTime": "2025-12-15T17:00:00-05:00"}, "end": {"dateTime": "2025-12-15T18:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 4, "internal_only": False},
  {"summary": "Chad out", "id": "7sm78iiqga3uamu2tulb0cbtf1_20251208T200000Z", "start": {"dateTime": "2025-12-08T15:00:00-05:00"}, "end": {"dateTime": "2025-12-08T16:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "7sm78iiqga3uamu2tulb0cbtf1_20251215T200000Z", "start": {"dateTime": "2025-12-15T15:00:00-05:00"}, "end": {"dateTime": "2025-12-15T16:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "3m7pd70b4784vnc8qhlo0pj6e9_20251216T194500Z", "start": {"dateTime": "2025-12-16T13:45:00-05:00"}, "end": {"dateTime": "2025-12-16T16:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "3m7pd70b4784vnc8qhlo0pj6e9_20251209T194500Z", "start": {"dateTime": "2025-12-09T14:45:00-05:00"}, "end": {"dateTime": "2025-12-09T16:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "3s8ealir0toshkjh72vnhqdvib_20251210T180000Z", "start": {"dateTime": "2025-12-10T13:00:00-05:00"}, "end": {"dateTime": "2025-12-10T14:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "3s8ealir0toshkjh72vnhqdvib_20251217T180000Z", "start": {"dateTime": "2025-12-17T13:00:00-05:00"}, "end": {"dateTime": "2025-12-17T14:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "1s5307g9363gpkgjofbggn84cf_20251211T200000Z", "start": {"dateTime": "2025-12-11T15:00:00-05:00"}, "end": {"dateTime": "2025-12-11T17:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "1s5307g9363gpkgjofbggn84cf_20251218T200000Z", "start": {"dateTime": "2025-12-18T15:00:00-05:00"}, "end": {"dateTime": "2025-12-18T17:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "5v0v3plmbl0b3ssbd5op70k77s_20251219T200000Z", "start": {"dateTime": "2025-12-19T11:30:00-05:00"}, "end": {"dateTime": "2025-12-19T12:45:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Chad out", "id": "5v0v3plmbl0b3ssbd5op70k77s_20251212T200000Z", "start": {"dateTime": "2025-12-12T15:00:00-05:00"}, "end": {"dateTime": "2025-12-12T16:00:00-05:00"}, "locked": True, "protected": False, "flexible": False, "number_of_attendees": 0, "internal_only": True},
  {"summary": "Grants Team Meeting", "id": "b1sjj9bbt1vifahjmap46illgv_20251211T160000Z", "start": {"dateTime": "2025-12-11T11:00:00-05:00"}, "end": {"dateTime": "2025-12-11T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Grants Team Meeting", "id": "b1sjj9bbt1vifahjmap46illgv_20251218T160000Z", "start": {"dateTime": "2025-12-18T11:00:00-05:00"}, "end": {"dateTime": "2025-12-18T12:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Interview Finance -in office - Julieta", "id": "3vtgacegmsvfvh31kqp7tklg8s", "start": {"dateTime": "2025-12-11T09:30:00-05:00"}, "end": {"dateTime": "2025-12-11T10:30:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Concord Tech Capabilities Development Discussion", "id": "0f2t1rjk3mnti5acqt9gdclrn8_20251211T170000Z", "start": {"dateTime": "2025-12-11T12:00:00-05:00"}, "end": {"dateTime": "2025-12-11T13:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Concord Tech Capabilities Development Discussion", "id": "0f2t1rjk3mnti5acqt9gdclrn8_20251218T170000Z", "start": {"dateTime": "2025-12-18T12:00:00-05:00"}, "end": {"dateTime": "2025-12-18T13:00:00-05:00"}, "locked": False, "protected": True, "flexible": False, "number_of_attendees": 5, "internal_only": True},
  {"summary": "AI Design Thinking", "id": "rngm55t9hebrf99npg0oqjo65c_20251210T170000Z", "start": {"dateTime": "2025-12-10T12:00:00-05:00"}, "end": {"dateTime": "2025-12-10T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 6, "internal_only": False},
  {"summary": "AI Design Thinking", "id": "rngm55t9hebrf99npg0oqjo65c_20251217T170000Z", "start": {"dateTime": "2025-12-17T12:00:00-05:00"}, "end": {"dateTime": "2025-12-17T13:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 6, "internal_only": False},
  {"summary": "Chad/Hee-Sun", "id": "4cbpbsvt4b4k8m4cb9t4g1bl3m_20251217T201500Z", "start": {"dateTime": "2025-12-17T15:15:00-05:00"}, "end": {"dateTime": "2025-12-17T16:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Core Support ", "id": "4l4qsnaufsnuiar18579m71jju", "start": {"dateTime": "2025-12-15T15:30:00-05:00"}, "end": {"dateTime": "2025-12-15T16:15:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 5, "internal_only": True},
  {"summary": "Concord Consortium/Nellie Mae Foundation", "id": "7559o18afqn13iokopabj2faq5", "start": {"dateTime": "2025-12-17T10:00:00-05:00"}, "end": {"dateTime": "2025-12-17T11:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": False},
  {"summary": "Interview In office Finance -Amy", "id": "6st1tbg89fokl0iv2s90pavdb2", "start": {"dateTime": "2025-12-10T10:00:00-05:00"}, "end": {"dateTime": "2025-12-10T11:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 3, "internal_only": True},
  {"summary": "Chad & Leslie", "id": "0j0m3qej5nt75f6hn5elu7rmk8_20251208T190000Z", "start": {"dateTime": "2025-12-08T13:00:00-05:00"}, "end": {"dateTime": "2025-12-08T13:45:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True},
  {"summary": "Kate / Chad", "id": "6uhtevmd3ri7n5i5rv1pge7rin", "start": {"dateTime": "2025-12-08T14:15:00-05:00"}, "end": {"dateTime": "2025-12-08T15:00:00-05:00"}, "locked": False, "protected": False, "flexible": True, "number_of_attendees": 2, "internal_only": True}
]

# Convert events to tool format
leslie_events = [convert_event_format(e) for e in leslie_events_raw]
chad_events = [convert_event_format(e) for e in chad_events_raw]

# Build events_by_participant structure
events_by_participant = {
    "lbondaryk@concord.org": leslie_events,
    "cdorsey@concord.org": chad_events
}

# Build context_json
context_json = {
    "timeframe": {
        "from": "2025-12-08",
        "to": "2025-12-19",
        "tz": "America/New_York"
    },
    "participants": [
        {
            "id": "cdorsey@concord.org",
            "email": "cdorsey@concord.org",
            "work_hours": "M-F 09:00-17:00"
        },
        {
            "id": "lbondaryk@concord.org",
            "email": "lbondaryk@concord.org",
            "work_hours": "M-F 09:00-17:00"
        }
    ],
    "policy": {
        "hard": {
            "min_gap_min": 0
        }
    }
}

# Call the tool exactly as Letta would
utterance = "Find a 45-minute meeting for Chad Dorsey and Leslie Bondaryk between December 8 and December 19, minimizing disruption."

print("=" * 80)
print("Testing orchestrate_scheduling tool with Letta-style input")
print("=" * 80)
print()
print(f"Utterance: {utterance}")
print()
print(f"Participants: {len(events_by_participant)}")
print(f"  - cdorsey@concord.org: {len(chad_events)} events")
print(f"  - lbondaryk@concord.org: {len(leslie_events)} events")
print()

# Convert to JSON strings as the tool expects
events_json_str = json.dumps(events_by_participant)
context_json_str = json.dumps(context_json)

print("=" * 80)
print("INPUT FORMAT (mimicking Letta tool call)")
print("=" * 80)
print()
print("events_by_participant format:")
print(f"  Type: JSON string (length: {len(events_json_str)} chars)")
print(f"  Sample (first 200 chars): {events_json_str[:200]}...")
print()
print("context_json format:")
print(f"  Type: JSON string (length: {len(context_json_str)} chars)")
print(f"  Content: {context_json_str}")
print()
print("Key conversion notes:")
print("  - Events have 'start' and 'end' as ISO strings (not nested dateTime objects)")
print("  - Events have 'title' field (mapped from 'summary')")
print("  - All boolean values are Python booleans (not strings)")
print()

# Call the tool
print("Calling orchestrate_scheduling...")
print()

try:
    result = orchestrate_scheduling(
        utterance=utterance,
        events_by_participant=events_json_str,
        context_json=context_json_str
    )
    
    print("=" * 80)
    print("RESULT")
    print("=" * 80)
    print()
    print(f"Status: {result.get('status')}")
    print(f"Proposals found: {len(result.get('proposals', []))}")
    print(f"Explanation: {result.get('explanation')}")
    print()
    
    # Display user_display if available (this is what Letta should show to users)
    if result.get('user_display'):
        print("=" * 80)
        print("USER DISPLAY (what should be shown to end users)")
        print("=" * 80)
        print(result.get('user_display', {}).get('summary', ''))
        print()
        if result.get('user_display', {}).get('best_options'):
            print("Best Options:")
            for opt in result.get('user_display', {}).get('best_options', [])[:5]:
                print(f"  - {opt.get('time_display', '')} - {opt.get('description', '')}")
        print()
    
    if result.get('status') == 'ok' and result.get('proposals'):
        print("=" * 80)
        print("DETAILED PROPOSAL SUMMARY")
        print("=" * 80)
        print(f"Total proposals: {len(result.get('proposals', []))}")
        print()
        
        # Parse and display proposals in readable format
        from datetime import datetime
        import pytz
        
        et = pytz.timezone('America/New_York')
        
        print("Top 20 Meeting Options:")
        print("-" * 80)
        for i, prop in enumerate(result.get('proposals', [])[:20], 1):
            # Convert UTC to Eastern Time
            start_utc_str = prop.get('start_utc', '')
            if start_utc_str:
                try:
                    start_utc = datetime.fromisoformat(start_utc_str.replace('+00:00', '+00:00'))
                    if start_utc.tzinfo is None:
                        start_utc = pytz.UTC.localize(start_utc)
                    start_et = start_utc.astimezone(et)
                    end_utc = datetime.fromisoformat(prop.get('end_utc', '').replace('+00:00', '+00:00'))
                    if end_utc.tzinfo is None:
                        end_utc = pytz.UTC.localize(end_utc)
                    end_et = end_utc.astimezone(et)
                    
                    day_name = start_et.strftime('%A, %B %d, %Y')
                    time_range = f"{start_et.strftime('%I:%M %p')} - {end_et.strftime('%I:%M %p')} ET"
                    
                    category = prop.get('category', 'unknown')
                    moved = prop.get('moved_events', [])
                    
                    print(f"\n{i}. {day_name}")
                    print(f"   Time: {time_range}")
                    print(f"   Category: {category}")
                    
                    if not moved:
                        print(f"   Status: Free slot (no conflicts)")
                    else:
                        for move in moved:
                            owner = move.get('owner', '').split('@')[0]
                            shift_mins = move.get('shift_minutes', 0)
                            old_start = datetime.fromisoformat(move.get('old_start', '').replace('+00:00', '+00:00'))
                            if old_start.tzinfo is None:
                                old_start = pytz.UTC.localize(old_start)
                            old_start_et = old_start.astimezone(et)
                            new_start = datetime.fromisoformat(move.get('new_start', '').replace('+00:00', '+00:00'))
                            if new_start.tzinfo is None:
                                new_start = pytz.UTC.localize(new_start)
                            new_start_et = new_start.astimezone(et)
                            
                            direction = "earlier" if shift_mins < 0 else "later"
                            hours = abs(shift_mins) // 60
                            mins = abs(shift_mins) % 60
                            if hours > 0:
                                shift_desc = f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
                            else:
                                shift_desc = f"{mins}m"
                            
                            print(f"   Requires: Move {owner}'s event {shift_desc} {direction}")
                            print(f"             (from {old_start_et.strftime('%I:%M %p')} to {new_start_et.strftime('%I:%M %p')} ET)")
                except Exception as e:
                    print(f"{i}. {start_utc_str} | Error parsing time: {e}")
        
        print()
        print("=" * 80)
        print("CATEGORY BREAKDOWN")
        print("=" * 80)
        categories = {}
        for prop in result.get('proposals', []):
            cat = prop.get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count} options")
    elif result.get('status') != 'ok':
        print(f"Error: {result.get('error_message')}")
        if result.get('error_traceback'):
            print("\nTraceback:")
            print(result.get('error_traceback'))
    
    print()
    print("=" * 80)
    print("Full result (first 2000 chars):")
    print("=" * 80)
    print(json.dumps(result, indent=2)[:2000])
    print("...")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

