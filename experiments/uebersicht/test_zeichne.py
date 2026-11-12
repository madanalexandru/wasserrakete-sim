"""Tests für zeichne.py: Vollständigkeit, Layout ohne Überlappung, Reproduzierbarkeit.

Start (PowerShell, im Repo-Ordner):
    docker compose --profile experiment run --rm --no-deps experiment sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python -W error -m unittest discover -s uebersicht -v"
"""

import contextlib
import io
import itertools
import tempfile
import unittest
from pathlib import Path

import zeichne

MARGIN = 0.5  # mm, Mindestabstand von Text zum Rand seines Kastens
STEP = 0.1    # mm, Abtastung der Pfeile


def rect_of(key):
    if key in zeichne.BOXES:
        return zeichne.BOXES[key][0]
    return zeichne.FRAMES[key][0]


def parent_of(key):
    if key in zeichne.BOXES:
        return zeichne.BOXES[key][2]
    return zeichne.FRAMES[key][2]


def inside(inner, outer, margin=0.0):
    return (inner[0] >= outer[0] + margin and inner[1] >= outer[1] + margin
            and inner[2] <= outer[2] - margin and inner[3] <= outer[3] - margin)


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def in_interior(x, y, r):
    return r[0] < x < r[2] and r[1] < y < r[3]


def on_border(x, y, r, tol=1e-9):
    on_x = r[0] - tol <= x <= r[2] + tol and (abs(y - r[1]) < tol or abs(y - r[3]) < tol)
    on_y = r[1] - tol <= y <= r[3] + tol and (abs(x - r[0]) < tol or abs(x - r[2]) < tol)
    return on_x or on_y


def sample(points):
    """Punkte entlang des Linienzugs, ohne die ersten und letzten 0,5 mm."""
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        n = max(1, int(length / STEP))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]
    start, end = points[0], points[-1]
    far = lambda p, q: ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 > MARGIN
    return [p for p in out if far(p, start) and far(p, end)]


class Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib.pyplot as plt
        fig, texts = zeichne.draw()
        cls.extents = zeichne.text_extents(fig, texts)
        plt.close(fig)

    def test_all_parts_labeled(self):
        words = ["Browser", "Vanilla JS", "Nginx", "/api/", "FastAPI", "Pydantic",
                 "SQLAlchemy", "3 Phasen", "Ereignissuche", "Searchable", "PostgreSQL",
                 "Alembic", "Docker Compose", "Vorab-Notiz", "run.py", "data/",
                 "evaluate.py", "results/", "Bericht", "Referenztool",
                 "vor der Messung", "HTTP über Nginx", "direkter Aufruf der Physik"]
        text = " ".join([b[1] for b in zeichne.BOXES.values()]
                        + [f[1] for f in zeichne.FRAMES.values()]
                        + [n[2] for n in zeichne.NOTES]).replace("\n", " ")
        for w in words:
            self.assertIn(w, text)

    def test_everything_on_the_canvas(self):
        canvas = (0, 0, zeichne.WIDTH_MM, zeichne.HEIGHT_MM)
        for key in list(zeichne.BOXES) + list(zeichne.FRAMES):
            self.assertTrue(inside(rect_of(key), canvas), key)

    def test_children_inside_parents(self):
        for key in list(zeichne.BOXES) + list(zeichne.FRAMES):
            parent = parent_of(key)
            if parent is not None:
                self.assertTrue(inside(rect_of(key), rect_of(parent), margin=1.0), key)

    def test_siblings_do_not_overlap(self):
        keys = list(zeichne.BOXES) + list(zeichne.FRAMES)
        for a, b in itertools.combinations(keys, 2):
            if parent_of(a) == parent_of(b):
                self.assertFalse(overlap(rect_of(a), rect_of(b)), (a, b))

    def test_box_texts_fit(self):
        for kind, key, *bb in self.extents:
            if kind == "kasten":
                self.assertTrue(inside(bb, rect_of(key), MARGIN), key)

    def test_titles_and_notes_inside_frame_and_free(self):
        for kind, key, *bb in self.extents:
            if kind == "titel":
                frame = key
            elif kind == "hinweis":
                frame = zeichne.NOTES[key][4]
            else:
                continue
            self.assertTrue(inside(bb, rect_of(frame), MARGIN), (kind, key))
            for box in zeichne.BOXES:
                self.assertFalse(overlap(bb, rect_of(box)), (kind, key, box))
            for other in zeichne.FRAMES:
                if parent_of(other) == frame:
                    self.assertFalse(overlap(bb, rect_of(other)), (kind, key, other))

    def test_texts_do_not_overlap(self):
        for (k1, n1, *a), (k2, n2, *b) in itertools.combinations(self.extents, 2):
            self.assertFalse(overlap(a, b), ((k1, n1), (k2, n2)))

    def test_arrows_avoid_boxes_and_texts(self):
        for i, (points, _dashed) in enumerate(zeichne.ARROWS):
            for x, y in sample(points):
                for box in zeichne.BOXES:
                    self.assertFalse(in_interior(x, y, rect_of(box)), (i, box))
                for kind, key, *bb in self.extents:
                    self.assertFalse(in_interior(x, y, bb), (i, kind, key))

    def test_arrow_ends_touch_boxes(self):
        keys = list(zeichne.BOXES) + list(zeichne.FRAMES)
        for i, (points, _dashed) in enumerate(zeichne.ARROWS):
            for x, y in (points[0], points[-1]):
                self.assertTrue(any(on_border(x, y, rect_of(k)) for k in keys), (i, x, y))


class Main(unittest.TestCase):
    def run_main(self, out):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = zeichne.main(out)
        return code, buf.getvalue()

    def test_console_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "results"
            code, text = self.run_main(out)
            self.assertEqual(code, 0)
            self.assertEqual(text.splitlines(),
                             [f"geschrieben: results/{n}" for n in zeichne.OUTPUTS])
            for name in zeichne.OUTPUTS:
                self.assertGreater((out / name).stat().st_size, 0, name)

    def test_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            self.run_main(a)
            self.run_main(b)
            for name in zeichne.OUTPUTS:
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()