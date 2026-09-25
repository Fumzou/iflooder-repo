# -*- coding: utf-8 -*-
"""
Bande-son du sort GATOM, synchronisée à l'image près.

Génère `son/gatom_son.wav` (48 kHz, stéréo, 6 s) entièrement par synthèse :
aucun échantillon externe. Chaque son est placé à partir de la chronologie lue
dans `gatom_teleportation.py` (FPS, FRAME_END, F_TRACE, F_LIFT, F_CHARGE,
F_FLASH, F_GONE) : si vous déplacez le flash dans le script Blender, le son suit.

    pip install numpy scipy
    python son/gatom_son.py

Feuille de sons (image → son), effets seuls :
  1-31    tracé des 3 couches : grattement lumineux qui tourne de gauche à droite
  24/32/40 décollage des cercles flottants : souffle montant + grondement sourd
  60      la colonne jaillit : impact grave + grondement
  60-87   charge : montée de hauteur, souffle, crépitements électriques de plus en plus serrés
  84-88   aspiration (souffle inversé) puis silence de 20 ms
  88      TÉLÉPORTATION : boum grave, claquement, grésillement
  88-104  onde de choc : souffle qui balaie la stéréo en s'assombrissant
  94-106  la colonne se resserre en un fil : sifflement qui descend + souffle
  tout du long : crépitements aigus qui suivent la quantité de particules à l'écran

Aucun son n'a de note : ce ne sont que des bruitages (bruit filtré, impacts,
souffles), sauf la montée de la charge.

MUSIQUE = True ajoute la partie musicale : bourdon grave qui pulse avec la rotation
des cercles et cloches (ré-fa-la au tracé, la-fa-ré à la dissipation).
"""

import ast
import pathlib

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve

HERE = pathlib.Path(__file__).resolve().parent
SR = 48000
RNG = np.random.default_rng(1379)
MUSIQUE = False     # True : ajoute le bourdon et les cloches aux effets


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
T = np.arange(N) / SR

dry = np.zeros((2, N))
wet = np.zeros((2, N))


def at(frame):
    """Instant (s) où s'affiche l'image `frame` (l'image 1 est à 0 s)."""
    return (frame - 1) / FPS


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def curve(points, lt):
    xs, ys = zip(*points)
    return np.interp(lt, xs, ys)


def osc(freq, n, kind="sine", phase=0.0):
    ph = phase + 2 * np.pi * np.cumsum(np.broadcast_to(freq, (n,))) / SR
    if kind == "sine":
        return np.sin(ph)
    cyc = (ph / (2 * np.pi)) % 1.0
    if kind == "saw":
        return 2.0 * cyc - 1.0
    return 4.0 * np.abs(cyc - 0.5) - 1.0   # triangle


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
    if i0 >= N:
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


def bell(freq, dur=2.2, bright=1.0):
    n = int(dur * SR)
    lt = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp, decay in ((1.0, 1.0, 1.8), (2.0, 0.5, 1.2), (2.76, 0.35 * bright, 0.9),
                              (4.07, 0.2 * bright, 0.6), (5.4, 0.12 * bright, 0.4),
                              (6.8, 0.06 * bright, 0.3)):
        out += amp * np.sin(2 * np.pi * freq * ratio * lt + RNG.uniform(0, 6.28)) * np.exp(-lt / decay)
    return out * np.minimum(lt / 0.002, 1.0)


# ---------------------------------------------------------------------------
# Couches sonores
# ---------------------------------------------------------------------------

def drone():
    """Bourdon grave ; sa pulsation suit la vitesse de rotation des cercles."""
    tf = at(F_FLASH)
    rate = curve([(0, 1.2), (at(F_CHARGE), 3.0), (tf - 0.02, 12.0), (tf, 2.0), (DUR, 1.0)], T)
    trem = 0.72 + 0.28 * np.sin(2 * np.pi * np.cumsum(rate) / SR)
    cutoff = curve([(0, 140), (1.2, 480), (at(F_CHARGE), 650), (tf - 0.02, 2600),
                    (tf + 0.4, 700), (DUR, 180)], T)
    amp = curve([(0, 0), (1.3, 0.12), (at(F_CHARGE), 0.15), (tf - 0.06, 0.36), (tf - 0.02, 0.0),
                 (tf + 0.35, 0.0), (tf + 0.9, 0.11), (at(F_GONE), 0.0), (DUR, 0.0)], T)
    chans = []
    for det in (0.0, 0.43):
        x = np.zeros(N)
        for mult, d, a in ((0.5, 0.0, 0.7), (1.0, det, 1.0), (1.0, -0.31, 0.7),
                           (1.5, det * 0.5, 0.45), (2.0, 0.19, 0.35)):
            x += a * osc(73.42 * mult + d, N, "saw", RNG.uniform(0, 6.28))
        chans.append(svf(x, cutoff, 0.9) * trem * amp)
    place(np.vstack(chans), 0.0, gain=1.0, send=0.2)


def tracing():
    """Grattement lumineux pendant que chaque couche du cercle se dessine."""
    for i in range(3):
        start = at(F_TRACE + 5 * i)
        dur = (26 - 3 * i) / FPS
        n = int((dur + 0.25) * SR)
        lt = np.arange(n) / SR
        prog = np.clip(lt / dur, 0, 1)
        fc = 1300 * (1 + 0.3 * i) * (3.2 ** prog)
        x = svf(RNG.standard_normal(n), fc, 5.0, "band")
        jitter = np.abs(svf(RNG.standard_normal(n), np.full(n, 28.0), 0.7))
        x *= 0.35 + 3.0 * jitter
        e = np.minimum(lt / 0.06, 1) * np.clip((dur + 0.2 - lt) / 0.2, 0, 1)
        pan = 0.75 * np.sin(2 * np.pi * prog + i)       # le trait fait le tour du cercle
        place(x * e, start, pan, gain=0.2, send=0.3)
        if MUSIQUE:  # couche terminée : cloche (ré, fa, la)
            place(bell([587.33, 698.46, 880.0][i]), start + dur, pan=[-0.5, 0.0, 0.5][i],
                  gain=0.11, send=0.55)


def lifts():
    """Décollage des trois cercles flottants."""
    for i, f0 in enumerate(F_LIFT):
        start = at(f0)
        rise = 22 / FPS
        n = int((rise + 0.4) * SR)
        lt = np.arange(n) / SR
        prog = np.clip(lt / rise, 0, 1)
        whoosh = svf(RNG.standard_normal(n), 250 * (11 ** prog), 1.3, "band")
        e = np.sin(np.pi * np.clip(lt / (rise + 0.3), 0, 1)) ** 1.5
        place(whoosh * e, start, pan=np.linspace(-0.3, 0.3, n) * (1 if i % 2 else -1),
              gain=0.25, send=0.3)
        thrum = svf(RNG.standard_normal(n), 120 * (5 ** prog), 0.9)   # grondement sourd
        place(thrum * e, start, gain=0.4, send=0.25)
        if MUSIQUE:
            place(bell([1174.66, 1396.91, 1760.0][i], 1.6, 0.7), start + 0.35,
                  pan=[-0.35, 0.35, 0.0][i], gain=0.07, send=0.6)


def sparkles():
    """Crépitements aigus dont la densité suit la poussière de mana à l'écran."""
    dust = [(at(4), 0.0), (at(26), 1.0), (at(F_FLASH - 4), 1.4), (at(F_FLASH), 2.3),
            (at(F_FLASH + 12), 0.8), (at(FRAME_END - 4), 0.0)]
    step = 0.005
    for s in np.arange(0, DUR, step):
        rate = 7.0 * float(np.interp(s, *zip(*dust)))
        if RNG.random() < rate * step:
            d = RNG.uniform(0.005, 0.025)
            n = int(d * SR)
            tick = svf(RNG.standard_normal(n), np.full(n, RNG.uniform(4000, 9000)), 3.0, "band")
            tick *= np.exp(-np.arange(n) / (n / 4))
            place(tick, s, pan=RNG.uniform(-0.9, 0.9), gain=RNG.uniform(0.08, 0.2), send=0.45)


def charge():
    """La colonne jaillit puis la mana se concentre jusqu'au flash."""
    t0, tf = at(F_CHARGE), at(F_FLASH) - 0.02
    n = int((tf - t0) * SR)
    lt = np.arange(n) / SR
    prog = lt / (tf - t0)
    end_fade = np.clip((tf - t0 - lt) / 0.01, 0, 1)
    # jaillissement de la colonne : impact grave + grondement
    m = int(0.6 * SR)
    lm = np.arange(m) / SR
    thump = np.sin(2 * np.pi * np.cumsum(40 + 25 * np.exp(-lm / 0.08)) / SR) * np.exp(-lm / 0.25)
    place(np.tanh(2 * thump), t0, gain=0.3, send=0.2)
    roar = svf(RNG.standard_normal(n), 180 + 700 * np.minimum(prog * 1.8, 1), 0.8)
    grow = 16 / (FPS * (tf - t0))
    roar_env = np.where(prog < grow, (prog / grow) ** 0.7, 1.0 - 0.5 * (prog - grow) / (1 - grow))
    place(roar * roar_env * end_fade, t0, gain=0.24, send=0.25)
    # montée de hauteur avec trémolo qui accélère
    f = expo(110, 880, n)
    tone = svf(osc(f, n, "saw") + osc(f * 1.005, n), f * 4, 0.8)
    trem = 0.6 + 0.4 * np.sin(2 * np.pi * np.cumsum(4 + 18 * prog ** 2) / SR)
    place(tone * trem * prog ** 1.8 * end_fade, t0, gain=0.45, send=0.3)
    # souffle qui monte
    riser = svf(RNG.standard_normal(n), expo(300, 7000, n), 0.9, "band")
    place(riser * prog ** 1.8 * end_fade, t0, pan=0.0, gain=0.7, send=0.35)
    # crépitements électriques de plus en plus serrés
    step = 0.002
    for s in np.arange(0, tf - t0, step):
        rate = 4 + 70 * (s / (tf - t0)) ** 2
        if RNG.random() < rate * step:
            k = int(RNG.uniform(0.002, 0.009) * SR)
            burst = svf(RNG.standard_normal(k), np.full(k, RNG.uniform(2000, 6500)), 2.0, "band")
            place(burst * np.exp(-np.arange(k) / (k / 3)), t0 + s, pan=RNG.uniform(-1, 1),
                  gain=RNG.uniform(0.08, 0.25), send=0.2)
    # aspiration (souffle inversé) qui se termine pile avant l'impact
    a = int(0.45 * SR)
    rev = svf(RNG.standard_normal((2, a)).ravel(), np.full(2 * a, 3500.0), 0.7).reshape(2, a)
    rev *= np.exp(-np.arange(a) / (0.12 * SR))
    place(rev[:, ::-1] * 1.0, tf - 0.45, gain=0.4, send=0.3)


def impact():
    """Image du flash : la téléportation."""
    tf = at(F_FLASH)
    n = int(2.2 * SR)
    lt = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(35 + 70 * np.exp(-lt / 0.12)) / SR)
    boom = np.tanh(2.2 * boom * np.exp(-lt / 0.55)) * np.minimum(lt / 0.002, 1)
    place(boom, tf, gain=0.95, send=0.25)
    crack = svf(RNG.standard_normal((2, n)).ravel(), np.full(2 * n, 900.0), 0.7, "high").reshape(2, n)
    place(crack * np.exp(-lt / 0.025), tf, gain=0.45, send=0.5)
    body = svf(RNG.standard_normal((2, n)).ravel(), np.full(2 * n, 1500.0), 0.7).reshape(2, n)
    place(body * np.exp(-lt / 0.35), tf, gain=0.5, send=0.7)
    sizzle = svf(RNG.standard_normal((2, n)).ravel(), np.full(2 * n, 5000.0), 0.7, "high").reshape(2, n)
    flicker = 0.4 + 2.5 * np.abs(svf(RNG.standard_normal(n), np.full(n, 60.0), 0.7))
    place(sizzle * np.exp(-lt / 0.5) * flicker, tf, gain=0.16, send=0.6)
    # onde de choc : souffle qui s'assombrit et s'ouvre en stéréo
    m = int((16 / FPS + 0.4) * SR)
    lm = np.arange(m) / SR
    wave = svf(RNG.standard_normal((2, m)).ravel(), np.tile(expo(7000, 250, m), 2), 0.8).reshape(2, m)
    place(wave * np.exp(-lm / 0.3), tf, gain=0.35, send=0.4)


def collapse_and_fade():
    """La colonne se resserre en un fil, puis les cercles se dissipent."""
    t0, t1 = at(F_FLASH + 6), at(F_FLASH + 18)
    n = int((t1 - t0 + 0.1) * SR)
    lt = np.arange(n) / SR
    whistle = svf(RNG.standard_normal(n), expo(2400, 300, n), 8.0, "band")
    place(whistle * np.sin(np.pi * np.clip(lt / (t1 - t0), 0, 1)), t0, gain=0.3, send=0.4)
    m = int(0.25 * SR)
    puff = svf(RNG.standard_normal(m), np.full(m, 2000.0), 0.7) * np.exp(-np.arange(m) / (0.06 * SR))
    place(puff, t1, gain=0.25, send=0.5)
    if MUSIQUE:
        place(bell(1760.0, 1.4, 0.5), t1, gain=0.06, send=0.7)
    if MUSIQUE:  # cloches descendantes : le motif d'ouverture à l'envers
        for k, (fr, pan) in enumerate(((880.0, 0.5), (698.46, 0.0), (587.33, -0.5))):
            place(bell(fr, 2.0, 0.6), at(F_FLASH + 8 + 5 * k), pan=pan, gain=0.1, send=0.7)
        place(bell(293.66, 3.0, 0.4), at(F_GONE - 12), gain=0.13, send=0.6)


def reverb(x, seconds=2.4, rt60=2.0):
    n = int(seconds * SR)
    lt = np.arange(n) / SR
    ir = RNG.standard_normal((2, n)) * np.exp(-6.9 * lt / rt60)
    ir = np.vstack([svf(ch, np.full(n, 5000.0)) for ch in ir])
    ir[:, : int(0.015 * SR)] = 0.0                     # pré-délai
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
    return np.vstack([fftconvolve(x[c], ir[c])[:N] for c in range(2)])


def main():
    if MUSIQUE:
        drone()
    tracing()
    lifts()
    sparkles()
    charge()
    impact()
    collapse_and_fade()
    mix = dry + 0.9 * reverb(wet)
    mix -= mix.mean(axis=1, keepdims=True)
    mix /= np.abs(mix).max()
    mix = np.tanh(1.6 * mix) / np.tanh(1.6)            # saturation douce
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
