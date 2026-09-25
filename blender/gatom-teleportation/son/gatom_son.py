# -*- coding: utf-8 -*-
"""
Bande-son du sort GATOM, synchronisée à l'image près.

Génère `son/gatom_son.wav` (48 kHz, stéréo, 6 s) entièrement par synthèse, sans
aucun échantillon externe. Uniquement du bruitage et de l'ambiance : aucune note,
aucun accord, aucune mélodie. Tout est fait de bruit filtré, d'impacts, de souffles
et de crépitements.

Les instants sont lus dans `gatom_teleportation.py` (FPS, FRAME_END, F_TRACE,
F_LIFT, F_CHARGE, F_FLASH, F_GONE) : si vous déplacez le flash, le son suit.

    pip install numpy scipy
    python son/gatom_son.py

Feuille de bruitages (image → son) :
  tout du long  ambiance d'une salle de pierre (air, souffle lointain) et bourdonnement
                d'énergie du cercle, qui palpite à la vitesse de rotation des cercles
  1-31    le trait lumineux grave le sol : grésillement qui tourne autour du cercle ;
          chaque couche se scelle d'un « clonk » sourd (impact + déclic + grain de pierre)
  24-62   les cercles décollent (souffle qui monte) et se stabilisent (petit choc d'air)
  60      la colonne jaillit du sol : impact sourd, grondement, gravillons
  60-87   charge : rugissement d'énergie qui pulse de plus en plus vite, vent qui
          siffle en montant, arcs électriques de plus en plus serrés
  84-88   aspiration (souffle inversé) puis 25 ms de silence
  88      TÉLÉPORTATION : chute grave, claquement, souffle d'explosion, roulement de
          tonnerre, éclats de cristal
  88-104  onde de choc : souffle qui balaie la stéréo
  94-106  la colonne est aspirée en un fil (souffle qui plonge), puis « pop » quand il disparaît
  106-132 braises qui crépitent de moins en moins, l'ambiance revient seule
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
T = np.arange(N) / SR

dry = np.zeros((2, N))
wet = np.zeros((2, N))


def at(frame):
    """Instant (s) où s'affiche l'image `frame` (l'image 1 est à 0 s)."""
    return (frame - 1) / FPS


# ---------------------------------------------------------------------------
# Outils
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


def curve(points, lt):
    xs, ys = zip(*points)
    return np.interp(lt, xs, ys)


def expo(a, b, n):
    return a * (b / a) ** np.linspace(0.0, 1.0, n)


def noise(n, stereo=False):
    return RNG.standard_normal((2, n)) if stereo else RNG.standard_normal(n)


def wobble(n, rate):
    """Modulation aléatoire entre 0 et 1, qui change `rate` fois par seconde."""
    k = int(n / SR * rate) + 2
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), RNG.random(k))


def filt2(x, fc, q=0.7, mode="low"):
    """svf appliqué à un signal stéréo (2×n)."""
    return np.vstack([svf(ch, fc, q, mode) for ch in x])


def place(sig, start, pan=0.0, gain=1.0, send=0.25):
    """Ajoute un son mono (ou stéréo 2×n) au mix, avec panoramique à puissance constante."""
    i0 = int(round(start * SR))
    if i0 >= N:
        return
    if i0 < 0:
        sig = sig[..., -i0:]
        i0 = 0
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


def thud(f0, f1, decay, drive=2.0):
    """Impact sourd : une chute de pression très grave, pas une note."""
    n = int(decay * 6 * SR)
    lt = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-lt / (decay * 0.3))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-lt / decay)
    return np.tanh(drive * y * np.minimum(lt / 0.002, 1.0)) / np.tanh(drive)


def click(dur=0.012, fc=3000.0, q=1.5):
    n = int(dur * SR)
    return svf(noise(n), np.full(n, fc), q, "band") * np.exp(-np.arange(n) / (n / 5))


def grit(dur, fc=1200.0, decay=0.08):
    """Grain de pierre : bruit sourd très court."""
    n = int(dur * SR)
    return svf(noise(n), np.full(n, fc), 0.8) * np.exp(-np.arange(n) / (decay * SR))


def whoosh(dur, f0, f1, q=1.2, shape=1.5):
    n = int(dur * SR)
    lt = np.arange(n) / SR
    x = svf(noise(n), expo(f0, f1, n), q, "band")
    return x * np.sin(np.pi * np.clip(lt / dur, 0, 1)) ** shape


def crackles(t0, t1, rate_fn, fmin, fmax, gmin, gmax, dmin=0.002, dmax=0.01, send=0.25):
    """Crépitements aléatoires : densité donnée par rate_fn(progression 0→1)."""
    step = 0.002
    for s in np.arange(t0, t1, step):
        if RNG.random() < rate_fn((s - t0) / (t1 - t0)) * step:
            k = int(RNG.uniform(dmin, dmax) * SR)
            b = svf(noise(k), np.full(k, RNG.uniform(fmin, fmax)), 2.0, "band")
            place(b * np.exp(-np.arange(k) / (k / 3)), s, pan=RNG.uniform(-1, 1),
                  gain=RNG.uniform(gmin, gmax), send=send)


# ---------------------------------------------------------------------------
# Ambiance
# ---------------------------------------------------------------------------

def ambience():
    """Air d'une grande salle de pierre : souffle doux qui ondule."""
    gust = 0.5 + 0.5 * wobble(N, 1.5)
    air = filt2(noise(N, True), np.full(N, 420.0), 0.7) * gust
    fade = curve([(0, 0), (0.4, 1), (DUR - 0.3, 1), (DUR, 0)], T)
    place(air * fade, 0.0, gain=0.09, send=0.3)


def energy_field():
    """Bourdonnement d'énergie du cercle (bruit filtré), qui palpite avec la rotation."""
    tf = at(F_FLASH)
    rate = curve([(0, 2.0), (at(F_CHARGE), 4.0), (tf - 0.03, 15.0), (tf, 3.0), (DUR, 2.0)], T)
    flutter = 0.65 + 0.35 * np.sin(2 * np.pi * np.cumsum(rate) / SR)
    level = curve([(0, 0), (1.2, 0.8), (at(F_CHARGE), 1.0), (tf - 0.05, 1.8), (tf - 0.025, 0),
                   (tf + 0.3, 0), (tf + 0.8, 0.5), (at(F_GONE), 0), (DUR, 0)], T)
    low = filt2(noise(N, True), np.full(N, 140.0), 2.0, "band")
    fizz = filt2(noise(N, True), curve([(0, 2500), (tf, 6000), (DUR, 3000)], T), 1.0, "band")
    place((low + 0.12 * fizz) * flutter * level, 0.0, gain=0.32, send=0.25)


# ---------------------------------------------------------------------------
# Les étapes du sort
# ---------------------------------------------------------------------------

def seal_lock(t, pan, strength):
    """Une couche du cercle se scelle : « clonk » sourd + déclic + grain de pierre."""
    place(thud(95, 48, 0.1), t, pan=pan * 0.3, gain=0.35 * strength, send=0.25)
    place(click(0.01, 2600, 2.0), t, pan=pan, gain=0.4 * strength, send=0.3)
    place(grit(0.12, 900, 0.03), t + 0.004, pan=pan, gain=0.25 * strength, send=0.3)
    place(grit(0.6, 180, 0.2), t, pan=pan * 0.5, gain=0.25 * strength, send=0.4)


def tracing():
    """Le trait de lumière grave le sol : grésillement qui fait le tour du cercle."""
    for i in range(3):
        start = at(F_TRACE + 5 * i)
        dur = (26 - 3 * i) / FPS
        n = int((dur + 0.1) * SR)
        lt = np.arange(n) / SR
        prog = np.clip(lt / dur, 0, 1)
        grain = wobble(n, 45) ** 2
        sizzle = svf(noise(n), 2200 + 3000 * prog, 0.8, "high") * (0.2 + 1.6 * grain)
        env = np.minimum(lt / 0.04, 1) * np.clip((dur + 0.08 - lt) / 0.08, 0, 1)
        pan = 0.8 * np.sin(2 * np.pi * prog + i)            # le trait fait le tour du cercle
        place(sizzle * env, start, pan, gain=0.07, send=0.25)
        crackles(start, start + dur, lambda p: 70, 3000, 8000, 0.03, 0.08)
        seal_lock(start + dur, [-0.5, 0.5, 0.0][i], [0.8, 0.9, 1.0][i])


def lifts():
    """Les cercles décollent (souffle qui monte) puis se stabilisent (choc d'air)."""
    for i, f0 in enumerate(F_LIFT):
        start = at(f0)
        rise = 22 / FPS
        side = 1 if i % 2 else -1
        n = int((rise + 0.2) * SR)
        place(whoosh(rise + 0.2, 220, 3200, 1.0), start,
              pan=np.linspace(-0.4, 0.4, n) * side, gain=0.36, send=0.3)
        place(whoosh(0.35, 80, 400, 0.8, 1.0), start, gain=0.3, send=0.1)   # l'air se déplace
        place(thud(70, 45, 0.06, 1.5), start + rise, pan=0.3 * side, gain=0.18, send=0.2)
        place(grit(0.15, 2500, 0.03), start + rise, pan=0.3 * side, gain=0.1, send=0.4)


def charge():
    """La colonne jaillit, puis le sort se charge jusqu'au flash."""
    t0, tf = at(F_CHARGE), at(F_FLASH) - 0.025
    n = int((tf - t0) * SR)
    lt = np.arange(n) / SR
    prog = lt / (tf - t0)
    end = np.clip((tf - t0 - lt) / 0.006, 0, 1)
    # la colonne sort du sol : impact, grondement, gravillons, souffle qui monte
    place(thud(80, 34, 0.28), t0, gain=0.3, send=0.2)
    place(filt2(noise(int(1.2 * SR), True), np.full(int(1.2 * SR), 220.0), 0.8)
          * np.exp(-np.arange(int(1.2 * SR)) / (0.35 * SR)), t0, gain=0.25, send=0.3)
    crackles(t0, t0 + 0.6, lambda p: 90 * (1 - p), 500, 1800, 0.05, 0.14, 0.003, 0.015)
    place(whoosh(0.8, 150, 2400, 0.9), t0 - 0.05, gain=0.18, send=0.3)
    # rugissement d'énergie qui pulse de plus en plus vite
    pulse = 0.55 + 0.45 * np.sin(2 * np.pi * np.cumsum(3 + 14 * prog ** 1.5) / SR)
    roar = filt2(noise(n, True), 280 * (8 ** prog), 1.4, "band")
    place(roar * pulse * (0.45 + 0.55 * prog) * end, t0, gain=0.4, send=0.3)
    # vent qui siffle en montant
    wind = svf(noise(n), expo(900, 9500, n), 3.0, "band")
    place(wind * prog ** 1.4 * end, t0, pan=np.sin(2 * np.pi * 1.5 * lt) * 0.5, gain=0.28, send=0.35)
    # arcs électriques de plus en plus serrés
    crackles(t0, tf, lambda p: 6 + 90 * p ** 2, 2000, 7500, 0.06, 0.2, 0.002, 0.012, 0.2)
    # aspiration : souffle inversé qui s'arrête pile avant l'impact
    a = int(0.45 * SR)
    suck = filt2(noise(a, True), np.full(a, 4500.0), 0.7) * np.exp(-np.arange(a) / (0.1 * SR))
    place(suck[:, ::-1], tf - 0.45, gain=0.45, send=0.3)


def impact():
    """Image du flash : la téléportation."""
    tf = at(F_FLASH)
    place(thud(120, 28, 0.7, 2.5), tf, gain=0.95, send=0.2)             # chute grave
    m = int(0.25 * SR)
    lm = np.arange(m) / SR
    crack = filt2(noise(m, True), np.full(m, 1100.0), 0.7, "high") * np.exp(-lm / 0.018)
    place(crack, tf, gain=0.55, send=0.4)                                  # claquement
    k = int(0.9 * SR)
    blast = filt2(noise(k, True), expo(3500, 400, k), 0.7) * np.exp(-np.arange(k) / (0.22 * SR))
    place(blast, tf, gain=0.6, send=0.5)                                   # souffle d'explosion
    r = int(2.2 * SR)
    lr = np.arange(r) / SR
    roll = 0.4 + 0.9 * wobble(r, 7)
    thunder = filt2(noise(r, True), np.full(r, 260.0), 0.8) * roll * np.exp(-lr / 0.7)
    place(thunder * np.minimum(lr / 0.08, 1), tf + 0.03, gain=0.5, send=0.4)   # tonnerre
    # éclats de cristal : des bris de bruit très courts qui s'éparpillent
    crackles(tf + 0.01, tf + 0.9, lambda p: 110 * (1 - p) ** 2, 4000, 11000, 0.04, 0.12,
             0.004, 0.03, 0.55)
    # onde de choc
    w = int((16 / FPS + 0.4) * SR)
    lw = np.arange(w) / SR
    wave = filt2(noise(w, True), expo(8000, 220, w), 0.8) * np.exp(-lw / 0.32)
    place(wave, tf, gain=0.3, send=0.4)


def vanish():
    """La colonne est aspirée en un fil puis disparaît ; les braises retombent."""
    t0, t1 = at(F_FLASH + 6), at(F_FLASH + 18)
    n = int((t1 - t0) * SR)
    lt = np.arange(n) / SR
    prog = lt / (t1 - t0)
    suck = svf(noise(n), expo(3500, 180, n), 1.6, "band") * prog ** 1.2
    place(suck * np.clip((t1 - t0 - lt) / 0.01, 0, 1), t0, gain=0.3, send=0.3)
    place(thud(160, 60, 0.05, 1.5), t1, gain=0.3, send=0.3)               # « pop »
    place(click(0.008, 2000, 1.0), t1, gain=0.3, send=0.3)
    place(whoosh(0.3, 3000, 900, 0.8, 1.0), t1, gain=0.08, send=0.5)
    # braises qui crépitent de moins en moins
    crackles(t1, at(F_GONE) + 0.3, lambda p: 30 * (1 - p) ** 1.5, 1200, 4500, 0.03, 0.09,
             0.002, 0.006, 0.4)


def reverb(x, seconds=2.2, rt60=1.8):
    n = int(seconds * SR)
    lt = np.arange(n) / SR
    ir = RNG.standard_normal((2, n)) * np.exp(-6.9 * lt / rt60)
    ir = np.vstack([svf(ch, np.full(n, 5000.0)) for ch in ir])
    ir[:, : int(0.02 * SR)] = 0.0                      # pré-délai
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True))
    return np.vstack([fftconvolve(x[c], ir[c])[:N] for c in range(2)])


def main():
    ambience()
    energy_field()
    tracing()
    lifts()
    charge()
    impact()
    vanish()
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
