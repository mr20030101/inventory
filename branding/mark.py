"""Construct the SAIMS mark: isometric box, check mark on the front-left face (in that face's plane)."""
import json, math, sys

K = math.tan(math.radians(30))          # iso slope 0.5774
C = (60, 60)                             # centre vertex where the three faces meet
R = 42                                   # half-width of the hexagon
H = round(R * K, 2)                      # 24.25: rise of the top edges
V = 48                                   # height of the side faces
top_y = C[1] - H                         # top face: (60,top) (102,60-H...) — computed below
TOP = (60, C[1] - 2 * H)
UL, UR = (60 - R, C[1] - H), (60 + R, C[1] - H)
LL, LR, BOT = (60 - R, C[1] - H + V), (60 + R, C[1] - H + V), (60, C[1] + V)
# shift everything so the hexagon is vertically centred in 120
dy = 60 - (TOP[1] + BOT[1]) / 2
sh = lambda p: (round(p[0], 2), round(p[1] + dy, 2))
TOP, UL, UR, LL, LR, BOT, CEN = map(sh, (TOP, UL, UR, LL, LR, BOT, C))

def P(pts): return "M" + " L".join(f"{x:g} {y:g}" for x, y in pts) + " Z"

def inset(poly, d):
    """Shrink a convex polygon by d (offset each edge inward, intersect neighbours)."""
    n = len(poly); lines = []
    cx = sum(p[0] for p in poly) / n; cy = sum(p[1] for p in poly) / n
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1; L = math.hypot(ex, ey)
        nx, ny = -ey / L, ex / L
        if (cx - x1) * nx + (cy - y1) * ny < 0: nx, ny = -nx, -ny
        lines.append(((x1 + nx * d, y1 + ny * d), (ex, ey)))
    out = []
    for i in range(n):
        (p, r), (q, s) = lines[i - 1], lines[i]
        den = r[0] * s[1] - r[1] * s[0]
        t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / den
        out.append((round(p[0] + t * r[0], 2), round(p[1] + t * r[1], 2)))
    return out

def check_poly(a, b, c, t):
    """Thick check polyline a-b-c (face-local coords), mitred, as a closed polygon."""
    def off(p, q, d):
        ex, ey = q[0] - p[0], q[1] - p[1]; L = math.hypot(ex, ey)
        return (-ey / L * d, ex / L * d)
    def isect(p1, d1, p2, d2):
        den = d1[0] * d2[1] - d1[1] * d2[0]
        tt = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        return (p1[0] + tt * d1[0], p1[1] + tt * d1[1])
    h = t / 2
    n1, n2 = off(a, b, h), off(b, c, h)
    d1, d2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
    a_l, a_r = (a[0] + n1[0], a[1] + n1[1]), (a[0] - n1[0], a[1] - n1[1])
    c_l, c_r = (c[0] + n2[0], c[1] + n2[1]), (c[0] - n2[0], c[1] - n2[1])
    b_l = isect(a_l, d1, (b[0] + n2[0], b[1] + n2[1]), d2)
    b_r = isect(a_r, d1, (b[0] - n2[0], b[1] - n2[1]), d2)
    return [a_l, b_l, c_l, c_r, b_r, a_r]

def to_left_face(u, v):
    """Face-local (u along the top edge, v straight down) → page coords on the left face."""
    return (round(UL[0] + u, 2), round(UL[1] + u * K + v, 2))

def check(t, a=(7, 27), b=(17, 33.5), c=(33.5, 6)):
    return [to_left_face(*p) for p in check_poly(a, b, c, t)]

top = [TOP, UR, CEN, UL]; left = [UL, CEN, BOT, LL]; right = [CEN, UR, LR, BOT]
gap = 1.6  # half-gap between faces in the one-colour version
mark = {
    "viewBox": 120,
    "bounds": [UL[0], TOP[1], UR[0] - UL[0], BOT[1] - TOP[1]],
    "elements": [
        {"d": P(left), "role": "body"},
        {"d": P(right), "role": "shade"},
        {"d": P(top), "role": "accent"},
        {"d": P(check(7.5)), "role": "knockout"},
    ],
    "small": [
        {"d": P(left), "role": "body"},
        {"d": P(right), "role": "shade"},
        {"d": P(top), "role": "accent"},
        {"d": P(check(11, (5.5, 27), (17, 34.5), (35, 5))), "role": "knockout"},
    ],
    "mono": " ".join(P(inset(f, gap)) for f in (top, left, right)) + " " + P(check(7.5)),
}
json.dump(mark, sys.stdout, indent=1)
