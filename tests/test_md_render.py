"""How the dashboard renders STP markdown (pilot feedback, 2026-09: the plan
"lacks bullet points and paragraph division")."""
from test_mutating_routes import ui  # noqa: F401 — same import/env as the route tests

STP = """#### **2. Known Limitations**

- **RAW disk format is not supported**
  - VEP-401 non-goal
  - *Sign-off:* [Name/Date]

- [x] **Review Requirements**
  - *List the key D/S requirements reviewed:* offline backup
"""


def test_two_space_nested_lists_stay_nested():
    html = ui._md_to_html(STP)
    # The detail and sign-off are children of the limitation, not siblings.
    assert html.index("<ul>", html.index("RAW disk format")) < html.index("VEP-401 non-goal")
    assert html.count("<ul>") == 3


def test_task_list_items_render_as_checkboxes():
    html = ui._md_to_html(STP)
    assert "[x]" not in html
    assert '<li class="task">' in html
    assert '<span class="task-box">☑</span><strong>Review Requirements' in html


def test_task_glyph_cannot_smuggle_markup():
    html = ui._md_to_html("- [ ] <script>alert(1)</script> item\n")
    assert "<script>" not in html and "☐" in html
