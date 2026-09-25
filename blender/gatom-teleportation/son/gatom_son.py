# -*- coding: utf-8 -*-
"""
Bande-son du sort GATOM, synchronisée à l'image près.

Génère `son/gatom_son.wav` (48 kHz, stéréo, 6 s) entièrement par synthèse :
aucun échantillon externe, et pas de musique de fond. Ce ne sont que des effets
de sort, mais accordés entre eux. Pendant que le sort se prépare, tout est en
ré mineur (tendu, mystérieux) ; au moment de la téléportation, tout bascule en
ré majeur, et c'est cette résolution qui rend l'effet satisfaisant.

Les instants sont lus dans `gatom_teleportation.py` (FPS, FRAME_END, F_TRACE,
F_LIFT, F_CHARGE, F_FLASH, F_GONE) : si vous déplacez le flash, le son suit.

    pip install numpy scipy
    python son/gatom_son.py

Feuille de sons (image → son) :
  1-31    tracé des 3 couches : arpège cristallin qui monte et suit le trait autour
          du cercle ; chaque couche se verrouille avec un « clic » + cloche (ré, la, ré aigu)
  24-62   les cercles décollent (souffle + note qui glisse vers le haut) et se posent
          sur ré, fa, la : l'accord de ré mineur se construit cercle par cercle
  60      la colonne jaillit : « whoom » grave
  60-87   charge : son de Shepard qui semble monter sans fin, arpège qui accélère
          de gauche à droite, pulsations graves de plus en plus rapides
  84-88   l'accord final aspiré à l'envers, puis 25 ms de silence
  88      TÉLÉPORTATION : chute grave, « shing » métallique, accord de ré majeur
          qui s'ouvre, cascade de paillettes qui descend
  88-104  onde de choc : souffle qui balaie la stéréo
  94-106  la colonne se resserre en un fil : « vwoop » qui descend, puis un
          « tic » aigu quand le fil disparaît (le voyageur est parti)
  106-132 dernières paillettes qui retombent, de plus en plus rares
"""

import ast
import pathlib

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve

HERE = pathlib.Path(__file__).resolve().parent
SR = 48000
RNG = np.random.default_rng(1379)


def read_timeline():
    """Lit les constantes de chronologie du script Blender sans importer bpy."""
    names = {"FPS", "FRAME_END", "F_TRACE", "F_LIFT", "F_CHARGE", "F_FLASH", "F_GONE"}
    src = (HERE.parent / "gatom_teleportation.py").read_text(encoding="utf-8")
    values = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in names:
                values[target.id] = ast.literal_eval(node.value)
    return values


TL = read_timeline()
FPS, FRAME_END = TL["FPS"], TL["FRAME_END"]
F_TRACE, F_LIFT, F_CHARGE = TL["F_TRACE"], TL["F_LIFT"], TL["F_CHARGE"]
F_FLASH, F_GONE = TL["F_FLASH"], TL["F_GONE"]
DUR = FRAME_END / FPS
N = int(round(DUR * SR))

dry = np.zeros((2, N))
wet = np.zeros((2, N))


def at(frame):
    """Instant (s) où s'affiche l'image `frame` (l'image 1 est à 0 s)."""
    return (frame - 1) / FPS


def note(name):
    """Fréquence d'une note, ex. 'D5', 'F#4' (La4 = 440 Hz)."""
    steps = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    semis = steps[name[0]] + (1 if "#" in name else 0) + 12 * (int(name[-1]) - 4)
    return 440.0 * 2 ** (semis / 12)


MINEUR = [note(n) for n in ("D4", "F4", "A4", "D5", "F5", "A5", "D6", "F6", "A6", "D7")]
PENTA_MAJ = [note(n) for n in ("D5", "E5", "F#5", "A5", "B5", "D6", "E6", "F#6", "A6", "B6", "D7")]


# ---------------------------------------------------------------------------
# Outils de synthèse
# ---------------------------------------------------------------------------

def svf(x, fc, q=0.7, mode="low"):
    """Filtre à variables d'état (TPT), fréquence de coupure variable dans le temps."""
    fc = np.clip(np.broadcast_to(fc, x.shape), 20.0, SR * 0.45)
    g = np.tan(np.pi * fc / SR)
    k = 1.0 / q
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    low = np.empty_like(x)
    band = np.empty_like(x)
    ic1 = ic2 = 0.0
    for i in range(len(x)):
        v3 = x[i] - ic2
        v1 = a1[i] * ic1 + a2[i] * v3
        v2 = ic2 + a2[i] * ic1 + a3[i] * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        low[i], band[i] = v2, v1
    if mode == "low":
        return low
    if mode == "band":
        return band
    return x - k * band - low


def expo(a, b, n):
    return a * (b / a) ** np.linspace(0.0, 1.0, n)


def place(sig, start, pan=0.0, gain=1.0, send=0.25):
    """Ajoute un son mono (ou stéréo 2×n) au mix, avec panoramique à puissance constante."""
    i0 = int(round(start * SR))
    if i0 >= N or i0 < 0:
        return
    if sig.ndim == 1:
        n = min(len(sig), N - i0)
        p = np.broadcast_to(pan, sig.shape)[:n]
        theta = (np.clip(p, -1, 1) + 1.0) * np.pi / 4.0
        st = np.vstack([np.cos(theta), np.sin(theta)]) * sig[:n]
    else:
        n = min(sig.shape[1], N - i0)
        st = sig[:, :n]
    dry[:, i0:i0 + n] += gain * st
    wet[:, i0:i0 + n] += gain * send * st


def fm(freq, dur, ratio=2.0, index=2.5, idecay=0.06, adecay=0.4, attack=0.002):
    """Synthèse FM : pincé cristallin (ratio 2) ou cloche (ratio 3,5)."""
    n = int(dur * SR)
    lt = np.arange(n) / SR
    mod = index * np.exp(-lt / idecay) * np.sin(2 * np.pi * freq * ratio * lt)
    y = np.sin(2 * np.pi * freq * lt + mod) * np.exp(-lt / adecay)
    return y * np.minimum(lt / attack, 1.0)


def crystal(freq, dur=0.5):
    return fm(freq, dur, ratio=2.0, index=2.2, idecay=0.04, adecay=dur / 4)


def bell(freq, dur=2.0):
    return fm(freq, dur, ratio=3.5, index=3.5, idecay=0.5, adecay=dur / 3) \
        + 0.35 * fm(freq * 2.0, dur, ratio=1.4, index=1.5, idecay=0.2, adecay=dur / 6)


def click(dur=0.012):
    n = int(dur * SR)
    return svf(RNG.standard_normal(n), np.full(n, 3500.0), 1.5, "band") * np.exp(-np.arange(n) / (n / 5))


def whoosh(dur, f0, f1, q=1.2):
    n = int(dur * SR)
    lt = np.arange(n) / SR
    x = svf(RNG.standard_normal(n), expo(f0, f1, n), q, "band")
    return x * np.sin(np.pi * np.clip(lt / dur, 0, 1)) ** 1.5


def supersaw(freq, n, voices=5, spread=0.012):
    lt = np.arange(n) / SR
    out = np.zeros((2, n))
    for v in range(voices):
        det = 1.0 + spread * (v - (voices - 1) / 2) / ((voices - 1) / 2)
        saw = 2.0 * ((freq * det * lt + RNG.random()) % 1.0) - 1.0
        side = (v % 2) * 2 - 1 if v != voices // 2 else 0
        out[0] += saw * (1.0 - 0.35 * side)
        out[1] += saw * (1.0 + 0.35 * side)
    return out / voices


# ---------------------------------------------------------------------------
# Les étapes du sort
# ---------------------------------------------------------------------------

def tracing():
    """Arpège cristallin qui suit chaque couche du cercle en train de se dessiner."""
    for i in range(3):
        start = at(F_TRACE + 5 * i)
        dur = (26 - 3 * i) / FPS
        count = 9
        pool = MINEUR[i * 2: i * 2 + 6]
        for k in range(count):
            prog = k / (count - 1)
            fr = pool[int(prog * (len(pool) - 1) + 0.5)]
            pan = 0.8 * np.sin(2 * np.pi * prog + i)          # le trait fait le tour du cercle
            place(crystal(fr, 0.45), start + prog * dur * 0.95, pan=pan,
                  gain=0.06 + 0.03 * prog, send=0.35)
        # verrouillage de la couche : clic + cloche (ré, la, ré aigu)
        lock = start + dur
        place(click(), lock, pan=[-0.4, 0.4, 0.0][i], gain=0.35, send=0.2)
        place(bell([note("D5"), note("A5"), note("D6")][i], 1.8), lock,
              pan=[-0.4, 0.4, 0.0][i], gain=0.1, send=0.5)
    # souffle léger sous le tracé
    place(whoosh(1.3, 400, 3000, 0.9), 0.0, pan=0.0, gain=0.08, send=0.2)


def lifts():
    """Les cercles décollent puis se posent sur ré, fa, la : l'accord se construit."""
    for i, f0 in enumerate(F_LIFT):
        start = at(f0)
        rise = 22 / FPS
        target = [note("D5"), note("F5"), note("A5")][i]
        place(whoosh(rise + 0.2, 250, 3500, 1.1), start, pan=0.3 * (1 if i % 2 else -1),
              gain=0.16, send=0.3)
        n = int(rise * SR)
        lt = np.arange(n) / SR
        prog = lt / rise
        f = target / 2 ** (7 / 12) * 2 ** ((7 / 12) * np.sqrt(prog))   # glisse d'une quinte
        glide = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * prog) ** 2
        place(svf(glide, np.full(n, 3000.0)), start, gain=0.05, send=0.4)
        # le cercle se pose : cloche + petit pincé à l'octave
        place(bell(target, 1.6), start + rise, pan=[-0.5, 0.5, 0.0][i], gain=0.1, send=0.5)
        place(crystal(target * 2, 0.4), start + rise + 0.05, pan=[-0.5, 0.5, 0.0][i],
              gain=0.04, send=0.5)


def charge():
    """La colonne jaillit, puis le sort se charge jusqu'au flash."""
    t0, tf = at(F_CHARGE), at(F_FLASH) - 0.025
    n = int((tf - t0) * SR)
    lt = np.arange(n) / SR
    prog = lt / (tf - t0)
    end = np.clip((tf - t0 - lt) / 0.008, 0, 1)
    # « whoom » : la colonne sort du sol
    m = int(0.8 * SR)
    lm = np.arange(m) / SR
    whoom = np.sin(2 * np.pi * np.cumsum(38 + 45 * np.exp(-lm / 0.1)) / SR) * np.exp(-lm / 0.3)
    place(np.tanh(2.0 * whoom), t0, gain=0.24, send=0.2)
    place(whoosh(0.7, 150, 1800, 0.8), t0 - 0.05, gain=0.14, send=0.3)
    # son de Shepard : des octaves qui montent sans fin, de plus en plus vite
    octaves = 7
    climb = np.cumsum(0.5 + 2.8 * prog ** 1.5) / SR
    shep = np.zeros(n)
    for k in range(octaves):
        pos = (k + climb) % octaves
        freq = 55.0 * 2 ** pos
        weight = np.exp(-0.5 * ((pos - octaves / 2) / 1.3) ** 2)
        shep += weight * np.sin(2 * np.pi * np.cumsum(freq) / SR)
    place(shep * (0.3 + 0.7 * prog ** 1.2) * end, t0, gain=0.16, send=0.35)
    # arpège de ré mineur qui accélère et monte, en ping-pong gauche/droite
    rate = 6 + 26 * prog ** 1.4
    beats = np.flatnonzero(np.diff(np.floor(np.cumsum(rate) / SR)) > 0)
    for j, idx in enumerate(beats):
        p = idx / n
        fr = MINEUR[min(len(MINEUR) - 1, (j % 4) + int(p * 6))]
        place(crystal(fr, 0.25), t0 + idx / SR, pan=0.6 if j % 2 else -0.6,
              gain=0.05 + 0.05 * p, send=0.3)
    # pulsations graves qui accélèrent (le cœur du sort)
    beats = np.flatnonzero(np.diff(np.floor(np.cumsum(2.0 + 7.0 * prog ** 2) / SR)) > 0)
    for idx in beats:
        k = int(0.18 * SR)
        lk = np.arange(k) / SR
        thump = np.sin(2 * np.pi * np.cumsum(50 + 40 * np.exp(-lk / 0.02)) / SR) * np.exp(-lk / 0.07)
        place(thump, t0 + idx / SR, gain=0.12 + 0.2 * idx / n, send=0.05)
    # souffle qui monte
    riser = svf(RNG.standard_normal(n), expo(400, 9000, n), 0.9, "band")
    place(riser * prog ** 1.6 * end, t0, gain=0.26, send=0.35)
    # l'accord final aspiré à l'envers, puis silence
    a = int(0.5 * SR)
    rev = impact_chord(a)[:, ::-1]
    rev *= np.linspace(0, 1, a) ** 2
    place(rev, tf - 0.5, gain=0.35, send=0.4)


def impact_chord(n):
    """Accord de ré majeur (avec la neuvième) en « supersaw » filtré."""
    lt = np.arange(n) / SR
    chord = np.zeros((2, n))
    for name, amp in (("D3", 0.9), ("A3", 0.7), ("D4", 0.8), ("F#4", 0.6), ("A4", 0.55), ("E5", 0.35)):
        chord += amp * supersaw(note(name), n)
    cutoff = 700 + 5500 * np.exp(-lt / 0.35)
    chord = np.vstack([svf(ch, cutoff, 0.8) for ch in chord])
    return chord * np.exp(-lt / 0.9) * np.minimum(lt / 0.004, 1.0)


def impact():
    """Image du flash : la téléportation."""
    tf = at(F_FLASH)
    n = int(2.6 * SR)
    lt = np.arange(n) / SR
    # chute grave
    drop = np.sin(2 * np.pi * np.cumsum(32 + 90 * np.exp(-lt / 0.15)) / SR)
    place(np.tanh(2.5 * drop * np.exp(-lt / 0.6)) * np.minimum(lt / 0.002, 1), tf, gain=0.8, send=0.2)
    # « shing » métallique + claquement
    shing = fm(2200.0, 1.2, ratio=1.414, index=6.0, idecay=0.08, adecay=0.35)
    place(shing, tf, gain=0.07, send=0.6)
    m = int(0.2 * SR)
    crack = svf(RNG.standard_normal((2, m)).ravel(), np.full(2 * m, 1200.0), 0.7, "high").reshape(2, m)
    place(crack * np.exp(-np.arange(m) / (0.02 * SR)), tf, gain=0.35, send=0.4)
    # l'accord de ré majeur s'ouvre
    place(impact_chord(n), tf, gain=0.3, send=0.6)
    # cascade de paillettes qui descend
    for k in range(18):
        fr = PENTA_MAJ[len(PENTA_MAJ) - 1 - (k % len(PENTA_MAJ))]
        place(crystal(fr, 0.6), tf + 0.03 + k * 0.045 + RNG.uniform(0, 0.015),
              pan=RNG.uniform(-0.8, 0.8), gain=0.045 * (1 - k / 22), send=0.55)
    # onde de choc
    w = int((16 / FPS + 0.4) * SR)
    lw = np.arange(w) / SR
    wave = svf(RNG.standard_normal((2, w)).ravel(), np.tile(expo(7000, 250, w), 2), 0.8).reshape(2, w)
    place(wave * np.exp(-lw / 0.3), tf, gain=0.22, send=0.4)


def vanish():
    """La colonne devient un fil et disparaît : le voyageur est parti."""
    t0, t1 = at(F_FLASH + 6), at(F_FLASH + 18)
    n = int((t1 - t0) * SR)
    lt = np.arange(n) / SR
    prog = lt / (t1 - t0)
    f = expo(note("A5"), note("D4"), n)
    vwoop = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.25 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    place(vwoop * np.sin(np.pi * prog) ** 0.8, t0, gain=0.06, send=0.4)
    place(click(0.008), t1, gain=0.3, send=0.3)
    place(crystal(note("D7"), 0.8), t1, gain=0.05, send=0.7)
    place(crystal(note("A6"), 0.8), t1 + 0.09, gain=0.03, send=0.7)
    # dernières paillettes, de plus en plus rares
    s = t1 + 0.2
    while s < at(F_GONE):
        place(crystal(PENTA_MAJ[RNG.integers(3, len(PENTA_MAJ))], 0.5), s,
              pan=RNG.uniform(-0.9, 0.9), gain=0.02, send=0.6)
        s += RNG.uniform(0.12, 0.3) * (1 + 2 * (s - t1) / (at(F_GONE) - t1))


def reverb(x, seconds=2.6, rt60=2.2):
    n = int(seconds * SR)
    lt = np.arange(n) / SR
    ir = RNG.standard_normal((2, n)) * np.exp(-6.9 * lt / rt60)
    ir = np.vstack([svf(ch, np.full(n, 6000.0)) for ch in ir])
    ir[:, : int(0.02 * SR)] = 0.0                      # pré-délai
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
    return np.vstack([fftconvolve(x[c], ir[c])[:N] for c in range(2)])


def main():
    tracing()
    lifts()
    charge()
    impact()
    vanish()
    mix = dry + 0.9 * reverb(wet)
    mix -= mix.mean(axis=1, keepdims=True)
    mix /= np.abs(mix).max()
    mix = np.tanh(1.5 * mix) / np.tanh(1.5)            # saturation douce
    mix *= 0.89 / np.abs(mix).max()                     # crête à -1 dBFS
    fade = np.ones(N)
    fade[: int(0.005 * SR)] = np.linspace(0, 1, int(0.005 * SR))
    fade[-int(0.08 * SR):] = np.linspace(1, 0, int(0.08 * SR))
    mix *= fade
    out = HERE / "gatom_son.wav"
    wavfile.write(out, SR, (mix.T * 32767).astype(np.int16))
    print(f"{out.name} : {DUR:.2f} s, flash à {at(F_FLASH):.3f} s (image {F_FLASH})")


if __name__ == "__main__":
    main()
