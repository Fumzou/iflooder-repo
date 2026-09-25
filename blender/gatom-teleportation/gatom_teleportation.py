# -*- coding: utf-8 -*-
"""
GATOM (転移) : sortilège de téléportation
Fan-art inspiré de « The Misfit of Demon King Academy » (Maou Gakuin no Futekigousha).

Ce script construit TOUTE la scène dans Blender, sans aucun fichier externe :
  * un cercle magique au sol en 3 couches qui tournent en sens opposés
    (anneau runique, hexagramme avec cercles satellites, cœur heptagramme) ;
  * des runes procédurales qui écrivent l'incantation « GATOM » ;
  * 3 cercles flottants qui s'élèvent et forment un couloir vertical ;
  * une colonne de lumière, un flash de téléportation et une onde de choc ;
  * des particules de mana et des traînées lumineuses (Geometry Nodes) ;
  * caméra animée, éclairage, sol en pierre polie, brume volumétrique et
    post-traitement (bloom + aberration chromatique).

Compatible Blender 4.2 LTS → 5.x.

Utilisation
-----------
1. Dans Blender : onglet « Scripting » → Ouvrir ce fichier → ▶ (Run Script).
   Une nouvelle scène « GATOM » est créée ; lancez l'animation (Espace).
2. En ligne de commande :
     blender -b -P gatom_teleportation.py -- --save gatom.blend
     blender -b -P gatom_teleportation.py -- --render flash.png --frame 88
     blender -b -P gatom_teleportation.py -- --anim rendu/ --engine CYCLES
     blender -b -P gatom_teleportation.py -- --anim rendu/ --smooth 2   (48 i/s)
   Options : --palette anos|azur|abysse  --incantation TEXTE  --no-fog
             --samples N  --percent 50  --frames 1:144  --smooth N

La bande-son (son/gatom_son.wav, générée par son/gatom_son.py) est ajoutée
automatiquement au montage si elle est présente : l'animation se joue avec le son.
"""

import argparse
import math
import pathlib
import random
import sys

import bpy
import bmesh  # après bpy : requis quand bpy est utilisé comme module Python

# =============================================================================
# PARAMÈTRES (modifiez librement)
# =============================================================================

INCANTATION = "GATOM"      # texte écrit (en runes) dans les anneaux
SEED = 1379                # graine des runes : change la forme des glyphes
FPS = 24
FRAME_END = 144            # 6 secondes
PALETTE = "anos"
FOG = True                 # brume volumétrique (plus beau, plus lent)

PALETTES = {
    # Rouge sang / or / blanc chaud : l'esprit de la magie d'Anos Voldigoad
    "anos": dict(cercle=(1.0, 0.035, 0.025), accent=(1.0, 0.30, 0.05),
                 coeur=(1.0, 0.80, 0.66), brume=(0.9, 0.08, 0.06)),
    # Bleu-cyan : téléportation « classique »
    "azur": dict(cercle=(0.03, 0.30, 1.0), accent=(0.30, 0.85, 1.0),
                 coeur=(0.85, 0.95, 1.0), brume=(0.08, 0.30, 0.9)),
    # Violet / argent
    "abysse": dict(cercle=(0.40, 0.04, 1.0), accent=(0.95, 0.35, 1.0),
                   coeur=(0.95, 0.90, 1.0), brume=(0.35, 0.08, 0.9)),
}

# Chronologie (images, à 24 i/s)
F_TRACE = 1          # le cercle au sol commence à se dessiner
F_LIFT = (24, 32, 40)  # apparition des 3 cercles flottants
F_CHARGE = 60        # accumulation de mana, la colonne jaillit
F_FLASH = 88         # téléportation !
F_GONE = 132         # plus rien

TAU = math.tau
SEPARATOR = "·"


# =============================================================================
# OUTILS : animation (compatible 4.x et 5.x)
# =============================================================================

def _fcurves(idb):
    ad = idb.animation_data
    if ad is None or ad.action is None:
        return []
    act = ad.action
    try:
        return list(act.fcurves)          # Blender 4.x
    except AttributeError:
        from bpy_extras import anim_utils  # Blender 5.x (actions à slots)
        bag = anim_utils.action_get_channelbag_for_slot(act, ad.action_slot)
        return list(bag.fcurves) if bag else []


def key(owner, prop, frame, value, interp="BEZIER", easing=None):
    """Pose une clé sur owner.prop (prop peut être '["custom"]')."""
    if prop.startswith('["'):
        owner[prop[2:-2]] = value
    else:
        setattr(owner, prop, value)
    owner.keyframe_insert(data_path=prop, frame=frame)
    path = owner.path_from_id(prop)
    for fc in _fcurves(owner.id_data):
        if fc.data_path != path:
            continue
        for kp in fc.keyframe_points:
            if abs(kp.co.x - frame) < 0.5:
                kp.interpolation = interp
                if easing:
                    kp.easing = easing


def keys(owner, prop, pairs, interp="BEZIER"):
    for frame, value in pairs:
        key(owner, prop, frame, value, interp)


# =============================================================================
# OUTILS : construction de nœuds
# =============================================================================

class Nodes:
    """Petit assistant pour câbler des arbres de nœuds (shader ou géométrie)."""

    def __init__(self, tree):
        self.tree = tree
        self.n = 0

    def new(self, kind, **props):
        node = self.tree.nodes.new(kind)
        for k, v in props.items():
            setattr(node, k, v)
        node.location = (200 * (self.n % 8), -220 * (self.n // 8))
        self.n += 1
        return node

    def put(self, socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.tree.links.new(value, socket)
        elif value is not None:
            socket.default_value = value

    def math(self, op, a, b=None, c=None):
        node = self.new("ShaderNodeMath", operation=op)
        for sock, val in zip(node.inputs, (a, b, c)):
            self.put(sock, val)
        return node.outputs[0]

    def vec(self, x, y, z):
        node = self.new("ShaderNodeCombineXYZ")
        for sock, val in zip(node.inputs, (x, y, z)):
            self.put(sock, val)
        return node.outputs[0]

    def map_range(self, value, fmin, fmax, tmin, tmax):
        node = self.new("ShaderNodeMapRange", clamp=True)
        for name, val in (("Value", value), ("From Min", fmin), ("From Max", fmax),
                          ("To Min", tmin), ("To Max", tmax)):
            self.put(node.inputs[name], val)
        return node.outputs[0]

    def rand(self, lo, hi, seed, ident):
        node = self.new("FunctionNodeRandomValue", data_type="FLOAT")
        floats = [s for s in node.inputs if s.type == "VALUE"]
        self.put(floats[0], lo)   # Min
        self.put(floats[1], hi)   # Max
        self.put(node.inputs["ID"], ident)
        self.put(node.inputs["Seed"], seed)
        return [s for s in node.outputs if s.type == "VALUE"][0]


# =============================================================================
# MATÉRIAUX
# =============================================================================

def _use_nodes(idb):
    if bpy.app.version < (5, 0, 0):    # toujours actif (et déprécié) en 5.x
        idb.use_nodes = True


def _new_material(name):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    _use_nodes(mat)
    mat.node_tree.nodes.clear()
    mat.use_backface_culling = False
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"   # EEVEE (4.2+)
    return mat


def _additive(nb, strength_socket, color):
    """Transparent + Émission : lumière pure qui s'additionne (look anime)."""
    em = nb.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    nb.put(em.inputs["Strength"], strength_socket)
    tr = nb.new("ShaderNodeBsdfTransparent")
    add = nb.new("ShaderNodeAddShader")
    nb.put(add.inputs[0], tr.outputs[0])
    nb.put(add.inputs[1], em.outputs[0])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.put(out.inputs["Surface"], add.outputs[0])
    return em


def _fade(nb):
    """Lit la propriété personnalisée « fade » de l'objet (animée)."""
    attr = nb.new("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fade")
    return attr.outputs["Fac"]


def mat_glow(name, color, strength, use_fade=True):
    mat = _new_material(name)
    nb = Nodes(mat.node_tree)
    s = nb.math("MULTIPLY", _fade(nb), strength) if use_fade else strength
    _additive(nb, s, color)
    return mat


def mat_pillar(name, color, strength):
    """Colonne de lumière : dégradé vertical, bords brillants, stries qui montent."""
    mat = _new_material(name)
    nb = Nodes(mat.node_tree)
    tc = nb.new("ShaderNodeTexCoord")
    sep = nb.new("ShaderNodeSeparateXYZ")
    nb.put(sep.inputs[0], tc.outputs["Generated"])
    z = sep.outputs["Z"]
    top = nb.math("POWER", nb.math("SUBTRACT", 1.0, z), 1.6)
    bottom = nb.map_range(z, 0.0, 0.04, 0.0, 1.0)
    lw = nb.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.45
    edge = nb.math("MULTIPLY_ADD", nb.math("POWER", lw.outputs["Facing"], 2.0), 1.6, 0.25)
    mapping = nb.new("ShaderNodeMapping")
    nb.put(mapping.inputs["Vector"], tc.outputs["Object"])
    mapping.inputs["Scale"].default_value = (3.0, 3.0, 0.35)
    noise = nb.new("ShaderNodeTexNoise", noise_dimensions="4D")
    noise.inputs["Scale"].default_value = 2.2
    noise.inputs["Detail"].default_value = 3.0
    nb.put(noise.inputs["Vector"], mapping.outputs[0])
    keys(noise.inputs["W"], "default_value", [(1, 0.0), (FRAME_END, 5.0)], "LINEAR")
    keys(mapping.inputs["Location"], "default_value",
         [(1, (0.0, 0.0, 0.0)), (FRAME_END, (0.0, 0.0, -14.0))], "LINEAR")
    streak = nb.map_range(noise.outputs["Fac"], 0.35, 0.75, 0.35, 1.7)
    s = nb.math("MULTIPLY", nb.math("MULTIPLY", top, bottom), edge)
    s = nb.math("MULTIPLY", s, streak)
    s = nb.math("MULTIPLY", s, nb.math("MULTIPLY", _fade(nb), strength))
    _additive(nb, s, color)
    return mat


def mat_underglow(name, color, strength, radius):
    """Halo lumineux posé sur le sol, décroissance radiale."""
    mat = _new_material(name)
    nb = Nodes(mat.node_tree)
    tc = nb.new("ShaderNodeTexCoord")
    length = nb.new("ShaderNodeVectorMath", operation="LENGTH")
    nb.put(length.inputs[0], tc.outputs["Object"])
    d = nb.map_range(length.outputs["Value"], 0.0, radius, 1.0, 0.0)
    s = nb.math("MULTIPLY", nb.math("POWER", d, 2.4), nb.math("MULTIPLY", _fade(nb), strength))
    _additive(nb, s, color)
    return mat


def mat_floor(name):
    """Dalles de pierre sombre et polie, qui reflètent les cercles."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    _use_nodes(mat)
    nt = mat.node_tree
    nt.nodes.clear()
    nb = Nodes(nt)
    tc = nb.new("ShaderNodeTexCoord")
    vor = nb.new("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    vor.inputs["Scale"].default_value = 0.45
    vor.inputs["Randomness"].default_value = 0.35
    nb.put(vor.inputs["Vector"], tc.outputs["Object"])
    grout = nb.map_range(vor.outputs["Distance"], 0.0, 0.025, 1.0, 0.0)
    noise = nb.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 1.8
    noise.inputs["Detail"].default_value = 6.0
    nb.put(noise.inputs["Vector"], tc.outputs["Object"])
    rough = nb.map_range(noise.outputs["Fac"], 0.35, 0.7, 0.10, 0.42)
    rough = nb.math("MAXIMUM", rough, nb.math("MULTIPLY", grout, 0.8))
    base = nb.map_range(grout, 0.0, 1.0, 0.018, 0.004)
    bump = nb.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    nb.put(bump.inputs["Height"], nb.math("SUBTRACT", 1.0, grout))
    bsdf = nb.new("ShaderNodeBsdfPrincipled")
    col = nb.new("ShaderNodeCombineColor")
    for i in range(3):
        nb.put(col.inputs[i], base)
    nb.put(bsdf.inputs["Base Color"], col.outputs[0])
    nb.put(bsdf.inputs["Roughness"], rough)
    nb.put(bsdf.inputs["Normal"], bump.outputs[0])
    out = nb.new("ShaderNodeOutputMaterial")
    nb.put(out.inputs["Surface"], bsdf.outputs[0])
    return mat


def mat_fog(name, density):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    _use_nodes(mat)
    nt = mat.node_tree
    nt.nodes.clear()
    nb = Nodes(nt)
    vol = nb.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = 0.35
    out = nb.new("ShaderNodeOutputMaterial")
    nb.put(out.inputs["Volume"], vol.outputs[0])
    return mat


# =============================================================================
# GÉOMÉTRIE : rubans 2D → maillage (cercles, étoiles, runes)
# =============================================================================

def _diamond(cx, cy, r):
    return [(cx + r, cy), (cx, cy + r), (cx - r, cy), (cx, cy - r)]


def _arc(cx, cy, r, a0, a1, n=12):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n),
             cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def glyph_strokes(ch):
    """Rune déterministe pour un caractère : liste de (points uv dans [0,1]², fermé).

    Ce n'est pas l'écriture officielle de l'anime : c'est un alphabet inventé,
    généré à partir de la graine SEED. Une même lettre donne toujours la même rune.
    """
    if ch == SEPARATOR:
        return [(_diamond(0.5, 0.5, 0.3), True), (_diamond(0.5, 0.5, 0.09), True)]
    rng = random.Random(f"gatom:{SEED}:{ch}")
    strokes = []
    spine = rng.choice(["fourche", "portique", "psi", "oeil", "orbe", "trident", "cle"])
    if spine == "fourche":
        strokes.append(([(0.1, 1.0), (0.5, 0.55), (0.9, 1.0)], False))
        strokes.append(([(0.5, 0.55), (0.5, 0.0)], False))
    elif spine == "portique":
        strokes.append(([(0.12, 0.0), (0.12, 1.0), (0.88, 1.0), (0.88, 0.35)], False))
    elif spine == "psi":
        strokes.append(([(0.5, 0.0), (0.5, 1.0)], False))
        strokes.append((_arc(0.5, 0.62, 0.36, math.pi, TAU), False))
    elif spine == "oeil":
        strokes.append((_arc(0.5, 0.05, 0.62, math.radians(35), math.radians(145)), False))
        strokes.append((_arc(0.5, 0.95, 0.62, math.radians(215), math.radians(325)), False))
        strokes.append((_diamond(0.5, 0.5, 0.1), True))
    elif spine == "orbe":
        strokes.append((_arc(0.5, 0.58, 0.3, 0, TAU, 16)[:-1], True))
        strokes.append(([(0.5, 0.28), (0.5, 0.0)], False))
    elif spine == "trident":
        strokes.append(([(0.12, 1.0), (0.12, 0.5), (0.88, 0.5), (0.88, 1.0)], False))
        strokes.append(([(0.5, 1.0), (0.5, 0.0)], False))
    else:  # clé
        strokes.append(([(0.3, 0.0), (0.3, 1.0)], False))
        strokes.append((_arc(0.66, 0.74, 0.2, 0, TAU, 12)[:-1], True))
        strokes.append(([(0.3, 0.28), (0.75, 0.28)], False))
    for _ in range(rng.randint(1, 2)):
        kind = rng.choice(["bar", "dot", "hook", "tick", "arc"])
        if kind == "bar":
            v = rng.choice([0.2, 0.5, 0.8])
            strokes.append(([(rng.choice([0.0, 0.25]), v), (rng.choice([0.75, 1.0]), v)], False))
        elif kind == "dot":
            strokes.append((_diamond(rng.choice([0.15, 0.5, 0.85]),
                                     rng.choice([0.15, 0.5, 0.85]), 0.08), True))
        elif kind == "hook":
            s = rng.choice([1, -1])
            strokes.append(([(0.5 + 0.4 * s, 0.6), (0.5 + 0.4 * s, 0.2), (0.5 + 0.1 * s, 0.0)], False))
        elif kind == "tick":
            strokes.append(([(0.5, 0.5), (rng.choice([0.0, 1.0]), rng.choice([0.2, 0.8]))], False))
        else:
            top = rng.random() < 0.5
            strokes.append((_arc(0.5, 1.0 if top else 0.0, 0.28,
                                 math.pi if top else 0.0, TAU if top else math.pi, 8), False))
    return strokes


def _densify(pts, closed, step):
    out = []
    n = len(pts)
    for i in range(n if closed else n - 1):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        k = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step))
        out.extend((x0 + (x1 - x0) * j / k, y0 + (y1 - y0) * j / k) for j in range(k))
    if not closed:
        out.append(pts[-1])
    return out


class Sigil:
    """Accumule des traits lumineux (rubans plats dans le plan XY)."""

    def __init__(self):
        self.bm = bmesh.new()
        self.mat = 0          # index de matériau courant
        self.z = 0.0

    def ribbon(self, pts, width, closed=False):
        n = len(pts)
        if n < 2:
            return
        self.z += 0.0002     # léger décalage : pas de faces coplanaires
        hw = width * 0.5

        def seg(i, j):
            dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
            d = math.hypot(dx, dy) or 1.0
            return dx / d, dy / d

        left, right = [], []
        for i in range(n):
            if closed:
                a, b = seg(i - 1, i), seg(i, (i + 1) % n)
            else:
                a = seg(max(i - 1, 0), max(i, 1)) if i > 0 else seg(0, 1)
                b = seg(i, i + 1) if i < n - 1 else a
            tx, ty = a[0] + b[0], a[1] + b[1]
            tl = math.hypot(tx, ty)
            tx, ty = (tx / tl, ty / tl) if tl > 1e-6 else b
            nx, ny = -ty, tx
            miter = hw / max(0.5, nx * -b[1] + ny * b[0])
            x, y = pts[i]
            left.append(self.bm.verts.new((x + nx * miter, y + ny * miter, self.z)))
            right.append(self.bm.verts.new((x - nx * miter, y - ny * miter, self.z)))
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            f = self.bm.faces.new((left[i], right[i], right[j], left[j]))
            f.material_index = self.mat

    # --- primitives -------------------------------------------------------
    def ring(self, r, w, cx=0.0, cy=0.0, seg=None):
        seg = seg or max(24, int(r * 90))
        self.ribbon(_arc(cx, cy, r, 0, TAU, seg)[:-1], w, closed=True)

    def disc(self, r, cx=0.0, cy=0.0):
        self.ring(r * 0.5, r, cx, cy, seg=24)

    def star(self, n, k, r, w, rot=0.0):
        """Polygone étoilé {n/k} (hexagramme = {6/2}, heptagramme = {7/3})."""
        g = math.gcd(n, k)
        for s in range(g):
            idx = [(s + i * k) % n for i in range(n // g)]
            pts = [(r * math.cos(rot + TAU * j / n), r * math.sin(rot + TAU * j / n)) for j in idx]
            self.ribbon(_densify(pts, True, 0.25), w, closed=True)

    def ticks(self, count, r0, r1, w, major_every=0, r_major=None):
        for i in range(count):
            a = TAU * i / count
            rin = r_major if (major_every and i % major_every == 0) else r0
            self.ribbon([(rin * math.cos(a), rin * math.sin(a)),
                         (r1 * math.cos(a), r1 * math.sin(a))], w)

    def spikes(self, count, r, length, half_angle, w, rot=0.0):
        for i in range(count):
            a = rot + TAU * i / count
            pts = [(r * math.cos(a - half_angle), r * math.sin(a - half_angle)),
                   ((r + length) * math.cos(a), (r + length) * math.sin(a)),
                   (r * math.cos(a + half_angle), r * math.sin(a + half_angle))]
            self.ribbon(pts, w)

    def glyph_band(self, text, r_in, h, stroke, aspect=0.62, gap=0.55, phase=0.0):
        """Écrit `text` en runes, en boucle, tout autour d'un anneau."""
        r_mid = r_in + h * 0.5
        tokens = list(text.upper()) + [SEPARATOR]
        slots = int(TAU * r_mid / (h * aspect * (1.0 + gap)))
        seq = tokens * max(1, slots // len(tokens))
        d_ang = TAU / len(seq)
        w_ang = h * aspect / r_mid
        for i, ch in enumerate(seq):
            ac = phase - i * d_ang
            for pts, closed in glyph_strokes(ch):
                pts = _densify(pts, closed, 0.12)
                xy = [((r_in + v * h) * math.cos(ac + (0.5 - u) * w_ang),
                       (r_in + v * h) * math.sin(ac + (0.5 - u) * w_ang)) for u, v in pts]
                self.ribbon(xy, stroke, closed)

    def satellite(self, cx, cy, r, w, outward):
        self.ring(r, w, cx, cy)
        self.ring(r * 0.74, w * 0.6, cx, cy)
        tri = [(cx + r * 0.7 * math.cos(outward + TAU * i / 3),
                cy + r * 0.7 * math.sin(outward + TAU * i / 3)) for i in range(3)]
        self.ribbon(tri, w * 0.6, closed=True)
        self.ribbon(_diamond(cx, cy, r * 0.14), w * 0.5, closed=True)

    # --- conversion --------------------------------------------------------
    def to_object(self, name, materials, collection, sweep_from=-math.pi / 2, clockwise=False):
        """Crée l'objet. Les faces sont triées par angle pour que le modificateur
        Build « trace » le cercle comme un balayage."""
        bm = self.bm

        def angle(f):
            c = f.calc_center_median()
            a = (math.atan2(c.y, c.x) - sweep_from) % TAU
            return TAU - a if clockwise else a

        bm.faces.sort(key=angle)
        bm.faces.index_update()
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for m in materials:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        collection.objects.link(ob)
        ob.visible_shadow = False
        ob["fade"] = 0.0
        return ob


# =============================================================================
# CONSTRUCTION DES CERCLES
# =============================================================================

def ground_layers(mats, coll):
    """Cercle principal au sol, en 3 couches indépendantes."""
    m_ring, m_glyph, m_core = mats

    # Couche 1 : anneau runique extérieur
    s = Sigil()
    s.ring(3.00, 0.055)
    s.ring(2.91, 0.018)
    s.spikes(8, 3.03, 0.22, 0.035, 0.022, rot=math.pi / 8)
    for i in range(24):
        a = TAU * i / 24
        s.ribbon(_diamond(3.0 * math.cos(a), 3.0 * math.sin(a), 0.055), 0.015, closed=True)
    s.mat = 1
    s.glyph_band(INCANTATION, 2.60, 0.24, 0.021)
    s.mat = 0
    s.ring(2.53, 0.030)
    s.ticks(120, 2.41, 2.49, 0.012, major_every=10, r_major=2.34)
    outer = s.to_object("Gatom_Sol_1_Anneau_Runique", [m_ring, m_glyph], coll)

    # Couche 2 : hexagramme + 6 cercles satellites
    s = Sigil()
    R = 2.10
    s.star(6, 2, R, 0.034, rot=math.pi / 2)
    s.ring(R, 0.020)
    s.ring(R / math.sqrt(3), 0.022)
    s.mat = 1
    for i in range(6):
        a = math.pi / 2 + TAU * i / 6
        s.satellite(R * math.cos(a), R * math.sin(a), 0.19, 0.02, a)
    hexa = s.to_object("Gatom_Sol_2_Hexagramme", [m_ring, m_glyph], coll, clockwise=True)

    # Couche 3 : cœur (runes internes + heptagramme + sceau central)
    s = Sigil()
    s.ring(1.04, 0.026)
    s.mat = 1
    s.glyph_band(INCANTATION, 0.86, 0.13, 0.013, phase=math.pi / 2)
    s.mat = 0
    s.ring(0.82, 0.016)
    s.star(7, 3, 0.80, 0.02, rot=math.pi / 2)
    s.ring(0.36, 0.02)
    s.ring(0.30, 0.012)
    s.mat = 2
    s.star(4, 1, 0.26, 0.014, rot=math.pi / 4)
    s.disc(0.07)
    core = s.to_object("Gatom_Sol_3_Coeur", [m_ring, m_glyph, m_core], coll)

    for ob, z in ((outer, 0.010), (hexa, 0.014), (core, 0.018)):
        ob.location.z = z
    return outer, hexa, core


def floating_circle(name, radius, variant, mats, coll):
    s = Sigil()
    s.ring(radius, 0.045)
    s.ring(radius - 0.075, 0.015)
    band = radius * 0.13
    r_band = radius - 0.10 - band
    s.mat = 1
    s.glyph_band(INCANTATION, r_band, band, max(0.011, band * 0.085), phase=variant)
    s.mat = 0
    r_in = r_band - 0.05
    s.ring(r_in, 0.022)
    if variant == 0:
        s.star(8, 3, r_in, 0.022)
        s.ring(r_in * 0.38, 0.018)
        s.ticks(48, r_in * 0.40, r_in * 0.47, 0.01)
    elif variant == 1:
        s.star(5, 2, r_in, 0.022, rot=math.pi / 2)
        s.ring(r_in * 0.40, 0.016)
    else:
        s.star(3, 1, r_in, 0.02, rot=math.pi / 2)
        s.star(3, 1, r_in, 0.02, rot=-math.pi / 2)
        s.ticks(36, r_in * 0.42, r_in * 0.5, 0.009)
    s.mat = 1
    s.spikes(4 + 2 * variant, radius + 0.02, radius * 0.1, 0.05, 0.016)
    return s.to_object(name, [mats[0], mats[1]], coll, clockwise=bool(variant % 2))


def simple_ring(name, radius, width, mat, coll):
    s = Sigil()
    s.ring(radius, width, seg=160)
    return s.to_object(name, [mat], coll)


def disc_object(name, radius, mat, coll, z=0.0):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=radius, segments=96)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.location.z = z
    ob.visible_shadow = False
    ob["fade"] = 0.0
    return ob


def cylinder_object(name, radius, height, mat, coll):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=64, radius1=radius,
                          radius2=radius, depth=height)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0.0, 0.0, height * 0.5))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.visible_shadow = False
    ob["fade"] = 0.0
    return ob


# =============================================================================
# PARTICULES (Geometry Nodes) : poussière de mana + traînées
# =============================================================================

def particles_object(coll, mat_mote, mat_streak):
    ng = bpy.data.node_groups.new("Gatom_Particules", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    s1 = ng.interface.new_socket("Poussiere", in_out="INPUT", socket_type="NodeSocketFloat")
    s2 = ng.interface.new_socket("Trainees", in_out="INPUT", socket_type="NodeSocketFloat")
    for s in (s1, s2):
        s.default_value, s.min_value, s.max_value = 1.0, 0.0, 10.0
    nb = Nodes(ng)
    gin = nb.new("NodeGroupInput")
    gout = nb.new("NodeGroupOutput")
    t = nb.new("GeometryNodeInputSceneTime").outputs["Seconds"]
    idx = nb.new("GeometryNodeInputIndex").outputs[0]

    def swarm(count, seed, r_min, r_max, r_pow, height, v_min, v_max, twist, converge,
              instance, size_min, size_max, stretch, intensity):
        rnd = lambda lo, hi, k: nb.rand(lo, hi, seed * 10 + k, idx)
        a0 = rnd(0.0, TAU, 1)
        r0 = nb.math("MULTIPLY_ADD", nb.math("POWER", rnd(0.0, 1.0, 2), r_pow), r_max - r_min, r_min)
        speed = nb.math("DIVIDE", rnd(v_min, v_max, 4), height)
        h = nb.math("FRACT", nb.math("MULTIPLY_ADD", t, speed, rnd(0.0, 1.0, 3)))
        ang = nb.math("ADD", nb.math("MULTIPLY_ADD", h, twist, a0), nb.math("MULTIPLY", t, 0.35))
        rad = nb.math("MULTIPLY", r0, nb.math("MULTIPLY_ADD", h, -converge, 1.0))
        pos = nb.vec(nb.math("MULTIPLY", nb.math("COSINE", ang), rad),
                     nb.math("MULTIPLY", nb.math("SINE", ang), rad),
                     nb.math("MULTIPLY", nb.math("POWER", h, 1.5), height))
        pts = nb.new("GeometryNodePoints")
        pts.inputs["Count"].default_value = count
        nb.put(pts.inputs["Position"], pos)
        env = nb.math("MULTIPLY", nb.math("MINIMUM", nb.math("MULTIPLY", h, 6.0), 1.0),
                      nb.math("POWER", nb.math("SUBTRACT", 1.0, h), 1.3))
        size = nb.math("MULTIPLY", nb.math("MULTIPLY", rnd(size_min, size_max, 5), env), intensity)
        inst = nb.new("GeometryNodeInstanceOnPoints")
        nb.put(inst.inputs["Points"], pts.outputs[0])
        nb.put(inst.inputs["Instance"], instance)
        nb.put(inst.inputs["Scale"], nb.vec(size, size, nb.math("MULTIPLY", size, stretch)))
        return inst.outputs["Instances"]

    ico = nb.new("GeometryNodeMeshIcoSphere")
    ico.inputs["Radius"].default_value = 1.0
    ico.inputs["Subdivisions"].default_value = 1
    m1 = nb.new("GeometryNodeSetMaterial")
    nb.put(m1.inputs["Geometry"], ico.outputs["Mesh"])
    m1.inputs["Material"].default_value = mat_mote

    cube = nb.new("GeometryNodeMeshCube")
    cube.inputs["Size"].default_value = (1.0, 1.0, 1.0)
    m2 = nb.new("GeometryNodeSetMaterial")
    nb.put(m2.inputs["Geometry"], cube.outputs["Mesh"])
    m2.inputs["Material"].default_value = mat_streak

    motes = swarm(380, 1, 0.25, 3.1, 0.7, 5.5, 0.5, 1.4, 1.3, 0.45,
                  m1.outputs[0], 0.008, 0.022, 1.0, gin.outputs[1])
    streaks = swarm(36, 2, 2.3, 3.05, 1.0, 6.5, 2.5, 5.0, 0.2, 0.1,
                    m2.outputs[0], 0.006, 0.011, 45.0, gin.outputs[2])
    join = nb.new("GeometryNodeJoinGeometry")
    nb.put(join.inputs[0], streaks)
    nb.put(join.inputs[0], motes)
    nb.put(gout.inputs[0], join.outputs[0])

    me = bpy.data.meshes.new("Gatom_Particules")
    ob = bpy.data.objects.new("Gatom_Particules", me)
    coll.objects.link(ob)
    mod = ob.modifiers.new("Particules", "NODES")
    mod.node_group = ng
    ob.visible_shadow = False
    return ob, mod, s1.identifier, s2.identifier


# =============================================================================
# SCÈNE
# =============================================================================

def fresh_scene():
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
    else:
        old = bpy.data.scenes.get("GATOM")
        scene = bpy.data.scenes.new("GATOM_tmp")
        bpy.context.window.scene = scene
        if old:
            for ob in list(old.collection.all_objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            for c in list(old.collection.children_recursive):
                bpy.data.collections.remove(c)
            bpy.data.scenes.remove(old)
            bpy.data.orphans_purge(do_recursive=True)
    scene.name = "GATOM"
    return scene


def new_collection(scene, name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


def setup_render(scene, engine):
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, FRAME_END
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.render.filepath = "//rendu/gatom_"
    engines = [e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items]
    eevee = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.render.engine = "CYCLES" if engine == "CYCLES" else eevee

    ee = scene.eevee
    for attr, val in (("taa_render_samples", 64), ("use_raytracing", True),
                      ("volumetric_tile_size", "4"), ("volumetric_samples", 96),
                      ("volumetric_end", 40.0), ("use_volumetric_shadows", True)):
        if hasattr(ee, attr):
            setattr(ee, attr, val)

    cy = scene.cycles
    cy.samples = 128
    cy.use_denoising = True
    cy.max_bounces = 6
    cy.transparent_max_bounces = 48
    cy.volume_bounces = 0
    cy.caustics_reflective = cy.caustics_refractive = False

    vs = scene.view_settings
    vs.view_transform = "AgX"
    try:
        vs.look = "AgX - Punchy"
    except TypeError:
        pass


def _glare(tree, gtype, **vals):
    node = tree.nodes.new("CompositorNodeGlare")
    labels = {"BLOOM": "Bloom", "STREAKS": "Streaks", "FOG_GLOW": "Fog Glow"}
    if "Type" in node.inputs:              # Blender 5.x
        node.inputs["Type"].default_value = labels[gtype]
        node.inputs["Quality"].default_value = "High"
    else:
        node.glare_type = gtype
        node.quality = "HIGH"
    legacy = {"Threshold": "threshold", "Streaks": "streaks", "Fade": "fade",
              "Streaks Angle": "angle_offset"}
    for name, val in vals.items():
        if name in node.inputs:
            node.inputs[name].default_value = val
        elif name == "Size":
            node.size = max(1, min(9, round(1 + val * 8)))
        elif name in legacy:
            setattr(node, legacy[name], val)
    return node


def setup_compositor(scene):
    if hasattr(scene, "compositing_node_group"):     # Blender 5.x
        tree = bpy.data.node_groups.new("Gatom_Compositing", "CompositorNodeTree")
        scene.compositing_node_group = tree
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        out = tree.nodes.new("NodeGroupOutput").inputs[0]
    else:
        scene.use_nodes = True
        tree = scene.node_tree
        tree.nodes.clear()
        out = tree.nodes.new("CompositorNodeComposite").inputs["Image"]
    rl = tree.nodes.new("CompositorNodeRLayers")
    bloom = _glare(tree, "BLOOM", Threshold=0.7, Strength=0.85, Size=0.8, Saturation=1.1)
    star = _glare(tree, "STREAKS", Threshold=30.0, Strength=0.5, Streaks=4,
                  Fade=0.93, **{"Streaks Angle": math.radians(45)})
    lens = tree.nodes.new("CompositorNodeLensdist")
    lens.inputs["Dispersion"].default_value = 0.012
    viewer = tree.nodes.new("CompositorNodeViewer")
    tree.links.new(rl.outputs["Image"], bloom.inputs["Image"])
    tree.links.new(bloom.outputs["Image"], star.inputs["Image"])
    tree.links.new(star.outputs["Image"], lens.inputs["Image"])
    tree.links.new(lens.outputs["Image"], out)
    tree.links.new(lens.outputs["Image"], viewer.inputs["Image"])
    for i, n in enumerate((rl, bloom, star, lens)):
        n.location = (i * 260, 0)
    viewer.location = (4 * 260, -200)
    out.node.location = (4 * 260, 100)


def setup_world(scene, fog, coll):
    world = bpy.data.worlds.new("Gatom_Nuit")
    scene.world = world
    _use_nodes(world)
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.0025, 0.0018, 0.004, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    if fog:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        me = bpy.data.meshes.new("Gatom_Brume")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat_fog("Gatom_Brume", 0.011))
        ob = bpy.data.objects.new("Gatom_Brume", me)
        coll.objects.link(ob)
        ob.scale = (26.0, 26.0, 9.0)
        ob.location.z = 4.5
        ob.hide_select = True
        ob.display_type = "WIRE"


def setup_camera(scene, coll):
    pivot = bpy.data.objects.new("Gatom_Camera_Pivot", None)
    target = bpy.data.objects.new("Gatom_Camera_Cible", None)
    cam_data = bpy.data.cameras.new("Gatom_Camera")
    cam_data.lens = 28
    cam = bpy.data.objects.new("Gatom_Camera", cam_data)
    for ob in (pivot, target, cam):
        coll.objects.link(ob)
    cam.parent = pivot
    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis, con.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    scene.camera = cam
    # lent travelling circulaire + léger rapprochement
    keys(pivot, "rotation_euler", [(1, (0, 0, math.radians(-14))),
                                    (FRAME_END, (0, 0, math.radians(14)))], "LINEAR")
    # vue plongeante pendant le tracé, puis contre-plongée pour la colonne de lumière
    keys(cam, "location", [(1, (0.0, -8.0, 7.2)), (F_CHARGE, (0.0, -9.0, 4.6)),
                           (FRAME_END, (0.0, -9.8, 2.4))])
    keys(target, "location", [(1, (0.0, 0.0, 0.3)), (F_CHARGE, (0.0, 0.0, 1.4)),
                              (F_FLASH - 2, (0.0, 0.0, 1.7))])
    # secousse au moment du flash
    shake = [(F_FLASH, (0.07, 0.0, 1.78)), (F_FLASH + 2, (-0.06, 0.02, 1.65)),
             (F_FLASH + 4, (0.03, -0.01, 1.74)), (F_FLASH + 7, (-0.01, 0.0, 1.71)),
             (F_FLASH + 11, (0.0, 0.0, 1.72)), (FRAME_END, (0.0, 0.0, 2.0))]
    keys(target, "location", shake)


def setup_lights(colors, coll):
    def point(name, loc, color, radius):
        ld = bpy.data.lights.new(name, "POINT")
        ld.color = color
        ld.shadow_soft_size = radius
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        coll.objects.link(ob)
        return ld

    glow = point("Gatom_Lueur_Sol", (0, 0, 0.45), colors["brume"], 1.6)
    keys(glow, "energy", [(1, 0.0), (24, 700.0), (F_CHARGE, 900.0), (F_FLASH - 2, 1800.0),
                          (F_FLASH, 6000.0), (F_FLASH + 12, 700.0), (F_GONE, 0.0)])
    flash_color = tuple(0.5 * (a + b) for a, b in zip(colors["coeur"], colors["brume"]))
    flash = point("Gatom_Flash", (0, 0, 1.6), flash_color, 0.4)
    keys(flash, "energy", [(F_FLASH - 3, 0.0), (F_FLASH, 7000.0), (F_FLASH + 5, 2500.0),
                           (F_FLASH + 18, 0.0)])
    rim_data = bpy.data.lights.new("Gatom_Contre_Jour", "AREA")
    rim_data.size = 8.0
    rim_data.energy = 250.0
    rim_data.color = (0.35, 0.4, 0.7)
    rim = bpy.data.objects.new("Gatom_Contre_Jour", rim_data)
    rim.location = (0.0, 9.0, 6.0)
    rim.rotation_euler = (math.radians(-55), 0.0, 0.0)
    coll.objects.link(rim)


# =============================================================================
# ANIMATION DU SORT
# =============================================================================

def build_spell(colors, coll):
    m_ring = mat_glow("Gatom_Trait", colors["cercle"], 14.0)
    m_glyph = mat_glow("Gatom_Rune", colors["accent"], 11.0)
    m_core = mat_glow("Gatom_Coeur", colors["coeur"], 18.0)
    mats = (m_ring, m_glyph, m_core)

    # --- cercle au sol ---------------------------------------------------
    layers = ground_layers(mats, coll)
    spins = (1.0, -1.25, 2.0)
    for i, ob in enumerate(layers):
        start = F_TRACE + 5 * i
        build = ob.modifiers.new("Trace", "BUILD")
        build.frame_start, build.frame_duration = start, 26 - 3 * i
        keys(ob, '["fade"]', [(start, 0.0), (start + 6, 1.0), (F_CHARGE, 1.0),
                              (F_FLASH - 2, 1.7), (F_FLASH, 3.0), (F_FLASH + 8, 1.2),
                              (F_GONE - 12, 0.0)])
        sp = spins[i]
        keys(ob, "rotation_euler", [(1, (0, 0, 0.0)), (F_CHARGE, (0, 0, 0.35 * sp)),
                                    (F_FLASH, (0, 0, 1.6 * sp)), (FRAME_END, (0, 0, 2.3 * sp))])
        keys(ob, "scale", [(start, (0.9,) * 3), (start + 22, (1.0,) * 3),
                           (F_FLASH, (1.0,) * 3), (F_FLASH + 14, (1.13,) * 3),
                           (F_GONE, (1.22,) * 3)])

    # --- cercles flottants -------------------------------------------------
    floats = ((1.25, 1.90), (2.45, 1.40), (3.55, 0.95))
    for i, ((height, radius), f0) in enumerate(zip(floats, F_LIFT)):
        ob = floating_circle(f"Gatom_Cercle_Flottant_{i + 1}", radius, i, mats, coll)
        build = ob.modifiers.new("Trace", "BUILD")
        build.frame_start, build.frame_duration = f0, 14
        sp = -1.0 if i % 2 == 0 else 1.0
        sp *= 1.4 + 0.5 * i
        keys(ob, '["fade"]', [(f0, 0.0), (f0 + 8, 1.5), (F_CHARGE, 1.5), (F_FLASH - 2, 2.2),
                              (F_FLASH, 3.6), (F_FLASH + 6, 1.6), (F_FLASH + 20, 0.0)])
        keys(ob, "location", [(f0, (0, 0, 0.05)), (f0 + 22, (0, 0, height)),
                              (F_FLASH, (0, 0, height)), (F_FLASH + 20, (0, 0, height + 0.6))])
        keys(ob, "rotation_euler", [(f0, (0, 0, 0.0)), (F_CHARGE, (0, 0, 0.5 * sp)),
                                    (F_FLASH, (0, 0, 2.4 * sp)), (FRAME_END, (0, 0, 3.2 * sp))])
        keys(ob, "scale", [(f0, (0.6,) * 3), (f0 + 16, (1.0,) * 3), (F_CHARGE + 6, (1.0,) * 3),
                           (F_FLASH - 2, (0.78,) * 3), (F_FLASH + 1, (1.05,) * 3),
                           (F_FLASH + 20, (1.45,) * 3)])

    # --- colonne de lumière -------------------------------------------------
    for name, radius, color, strength, peak in (
            ("Gatom_Colonne", 0.8, colors["cercle"], 6.0, 2.5),
            ("Gatom_Colonne_Coeur", 0.22, colors["coeur"], 12.0, 6.0)):
        mat = mat_pillar(name, color, strength)
        ob = cylinder_object(name, radius, 9.0, mat, coll)
        keys(ob, '["fade"]', [(F_CHARGE, 0.0), (F_CHARGE + 16, 1.0), (F_FLASH - 2, 1.6),
                              (F_FLASH + 1, peak), (F_FLASH + 12, 1.0), (F_FLASH + 24, 0.0)])
        keys(ob, "scale", [(F_CHARGE, (0.25, 0.25, 0.0)), (F_CHARGE + 14, (1.0, 1.0, 1.0)),
                           (F_FLASH - 2, (0.72, 0.72, 1.0)), (F_FLASH + 1, (1.7, 1.7, 1.1)),
                           (F_FLASH + 8, (0.5, 0.5, 1.2)), (F_FLASH + 18, (0.0, 0.0, 1.3))])

    # --- onde de choc + halo au sol ----------------------------------------
    wave = simple_ring("Gatom_Onde_De_Choc", 1.0, 0.022, m_core, coll)
    wave.location.z = 0.03
    keys(wave, '["fade"]', [(F_FLASH - 1, 0.0), (F_FLASH + 1, 2.5), (F_FLASH + 16, 0.0)])
    keys(wave, "scale", [(F_FLASH - 1, (0.8,) * 3), (F_FLASH + 16, (4.8,) * 3)])

    halo = disc_object("Gatom_Halo_Sol", 3.8, mat_underglow("Gatom_Halo", colors["brume"],
                                                          1.3, 3.8), coll, z=0.004)
    keys(halo, '["fade"]', [(1, 0.0), (24, 1.0), (F_CHARGE, 1.0), (F_FLASH - 2, 1.8),
                            (F_FLASH, 3.0), (F_FLASH + 12, 1.0), (F_GONE, 0.0)])

    # --- particules ----------------------------------------------------------
    m_mote = mat_glow("Gatom_Poussiere", colors["accent"], 14.0, use_fade=False)
    m_streak = mat_glow("Gatom_Trainee", colors["coeur"], 10.0, use_fade=False)
    _ob, mod, dust, trails = particles_object(coll, m_mote, m_streak)
    keys(mod, f'["{dust}"]', [(4, 0.0), (26, 1.0), (F_FLASH - 4, 1.4), (F_FLASH, 2.3),
                              (F_FLASH + 12, 0.8), (FRAME_END - 4, 0.0)])
    keys(mod, f'["{trails}"]', [(30, 0.0), (F_CHARGE, 1.0), (F_FLASH - 2, 1.6),
                                (F_FLASH + 8, 0.6), (F_GONE - 8, 0.0)])


def build_scene(palette=PALETTE, engine="EEVEE", fog=FOG):
    colors = PALETTES[palette]
    scene = fresh_scene()
    setup_render(scene, engine)
    c_spell = new_collection(scene, "GATOM_Sortilege")
    c_env = new_collection(scene, "GATOM_Decor")
    c_cam = new_collection(scene, "GATOM_Camera_Lumieres")

    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30.0)
    me = bpy.data.meshes.new("Gatom_Sol")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat_floor("Gatom_Pierre"))
    floor = bpy.data.objects.new("Gatom_Sol", me)
    c_env.objects.link(floor)

    setup_world(scene, fog, c_env)
    setup_camera(scene, c_cam)
    setup_lights(colors, c_cam)
    build_spell(colors, c_spell)
    setup_compositor(scene)
    add_soundtrack(scene)
    scene.frame_set(70)
    return scene


def add_soundtrack(scene):
    """Place son/gatom_son.wav à l'image 1 du montage, lecture synchronisée au son."""
    candidates = []
    if "__file__" in globals():
        candidates.append(pathlib.Path(__file__).resolve().parent / "son" / "gatom_son.wav")
    if bpy.data.filepath:
        candidates.append(pathlib.Path(bpy.path.abspath("//son/gatom_son.wav")))
    wav = next((c for c in candidates if c.is_file()), None)
    if wav is None:
        print("[GATOM] Pas de son/gatom_son.wav : scène sans bande-son.")
        return
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences  # 4.2-4.3
    strips.new_sound("Gatom_Son", str(wav), 1, scene.frame_start)
    scene.sync_mode = "AUDIO_SYNC"


def render_animation(scene, folder, smooth=1):
    """Rend l'animation. Avec smooth=N, Blender calcule N images par image
    (positions intermédiaires) : 2 donne 48 i/s pour une vidéo plus fluide."""
    folder = folder.rstrip("/")
    if smooth <= 1:
        scene.render.filepath = folder + "/gatom_"
        bpy.ops.render.render(animation=True)
        return
    n = 0
    for frame in range(scene.frame_start, scene.frame_end + 1):
        for k in range(smooth if frame < scene.frame_end else 1):
            scene.frame_set(frame, subframe=k / smooth)
            scene.render.filepath = f"{folder}/gatom_{n:04d}"
            bpy.ops.render.render(write_still=True)
            n += 1
    print(f"[GATOM] {n} images rendues : à assembler à {scene.render.fps * smooth} i/s.")


def show_in_viewport():
    """Vue caméra + ombrage « Rendu » (aussi enregistré dans le .blend)."""
    window = bpy.context.window
    screen = window.screen if window else bpy.data.screens.get("Layout")
    for area in (screen.areas if screen else []):
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.shading.type = "RENDERED"
            space.region_3d.view_perspective = "CAMERA"


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    elif sys.argv and sys.argv[0].endswith(".py"):
        argv = sys.argv[1:]            # python gatom_teleportation.py ... (module bpy)
    else:
        argv = []
    p = argparse.ArgumentParser(prog="gatom_teleportation.py")
    p.add_argument("--palette", choices=sorted(PALETTES), default=PALETTE)
    p.add_argument("--incantation", default=INCANTATION)
    p.add_argument("--engine", choices=["EEVEE", "CYCLES"], default="EEVEE")
    p.add_argument("--no-fog", action="store_true")
    p.add_argument("--samples", type=int)
    p.add_argument("--percent", type=int, help="taille du rendu en %% de 1920x1080")
    p.add_argument("--save", help="enregistre le .blend")
    p.add_argument("--render", help="rend une image fixe (voir --frame)")
    p.add_argument("--frame", type=int, default=F_FLASH)
    p.add_argument("--anim", help="rend l'animation dans ce dossier")
    p.add_argument("--frames", help="plage d'images, ex. 1:144")
    p.add_argument("--smooth", type=int, default=1,
                   help="images calculées par image avec --anim (2 = 48 i/s)")
    return p.parse_args(argv)


def main():
    global INCANTATION
    args = parse_args()
    INCANTATION = args.incantation
    scene = build_scene(args.palette, args.engine, fog=FOG and not args.no_fog)
    if args.samples:
        scene.cycles.samples = args.samples
        scene.eevee.taa_render_samples = args.samples
    if args.percent:
        scene.render.resolution_percentage = args.percent
    if args.frames:
        a, b = (int(x) for x in args.frames.split(":"))
        scene.frame_start, scene.frame_end = a, b
    show_in_viewport()
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(args.save), compress=True)
        print(f"[GATOM] Fichier enregistré : {args.save}")
    if args.render:
        scene.frame_set(args.frame)
        scene.render.filepath = args.render
        bpy.ops.render.render(write_still=True)
        print(f"[GATOM] Image {args.frame} rendue : {args.render}")
    if args.anim:
        render_animation(scene, args.anim, args.smooth)
    print("[GATOM] Scène prête.")


if __name__ == "__main__":
    main()
