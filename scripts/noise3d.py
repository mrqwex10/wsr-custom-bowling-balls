"""Vectorised 3D Perlin noise. Evaluated directly on sphere directions, so any
pattern built from it wraps around the ball with no seams or pole pinching."""
import numpy as np

_rng = np.random.default_rng(1234)
_PERM = np.tile(_rng.permutation(256), 2)
_GRAD = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1],
                  [1, 0, -1], [-1, 0, -1], [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1]], float)


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def perlin(p, seed=0):
    """p: (...,3) array. Returns noise in roughly [-1, 1]."""
    p = p + seed * 17.13
    pi = np.floor(p).astype(int)
    pf = p - pi
    pi &= 255
    X, Y, Z = pi[..., 0], pi[..., 1], pi[..., 2]
    u, v, w = _fade(pf[..., 0]), _fade(pf[..., 1]), _fade(pf[..., 2])

    def g(ix, iy, iz, dx, dy, dz):
        h = _PERM[_PERM[_PERM[(X + ix) & 255] + ((Y + iy) & 255)] + ((Z + iz) & 255)] % 12
        gr = _GRAD[h]
        return gr[..., 0] * (pf[..., 0] - dx) + gr[..., 1] * (pf[..., 1] - dy) + gr[..., 2] * (pf[..., 2] - dz)

    def lerp(a, b, t):
        return a + t * (b - a)

    x00 = lerp(g(0, 0, 0, 0, 0, 0), g(1, 0, 0, 1, 0, 0), u)
    x10 = lerp(g(0, 1, 0, 0, 1, 0), g(1, 1, 0, 1, 1, 0), u)
    x01 = lerp(g(0, 0, 1, 0, 0, 1), g(1, 0, 1, 1, 0, 1), u)
    x11 = lerp(g(0, 1, 1, 0, 1, 1), g(1, 1, 1, 1, 1, 1), u)
    return lerp(lerp(x00, x10, v), lerp(x01, x11, v), w)


def fbm(p, octaves=5, lac=2.0, gain=0.5, seed=0):
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for i in range(octaves):
        total = total + amp * perlin(p * freq, seed + i * 7)
        norm += amp
        amp *= gain
        freq *= lac
    return total / norm


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)
