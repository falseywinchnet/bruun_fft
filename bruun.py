"""Bruun radix-2 RFFT for N = 512 and its exact inverse, staged in the layout
of the unrolled Cooley-Tukey rfft: X_stage_j holds 2^j rows of length 512/2^j,
and one precomputed REAL coefficient table per level plays the role of the
twiddle table. All interior arithmetic is real; complex numbers appear only
when the 257 bins are written (forward) or read (inverse).

Forward. The tree factors z^512 - 1 over the reals. Node 0 of each level is
the binomial chain z^M - 1 -> (z^{M/2} - 1)(z^{M/2} + 1); every other node is
a trinomial z^D - 2 cos(beta) z^{D/2} + 1, which splits with half angles,
beta -> beta/2 and pi - beta/2 (z^M + 1 enters the trinomial world as
beta = pi/2). A level transition is reduction of each parent residue modulo
its two children, a two-cascade fold with real coefficients -+2 cos(beta/2).
The degree-2 leaves z^2 - 2 cos(beta) z + 1 own the conjugate root pair
e^{+-i beta}; evaluating the linear residue r0 + r1 z at z = e^{-i beta}
yields bin k = beta*512/(2 pi). Node 0 ends as (z-1)(z+1), bins 0 and 256.

Inverse. Each forward level is a ring isomorphism R[z]/(p1 p2) ->
R[z]/(p1) x R[z]/(p2); its inverse is Chinese-remainder reconstruction. For
trinomial children p1 = z^h - b z^{h/2} + 1, p2 = z^h + b z^{h/2} + 1 with
b = 2 cos(beta/2), the Bezout data is closed form: p1 - p2 = -2 b z^{h/2}
and z^{-h/2} = -(z^{h/2} + b) mod p2, hence
    t = ((r2 - r1)(z^{h/2} + b) mod p2) / (2 b),     c = r1 + p1 t.
For the binomial pair, p1 - p2 = -2 gives t = (r1 - r2)/2 and
c = r1 + (z^{M/2} - 1) t. Sweeping leaves to root recovers x exactly; no
1/N normalization exists anywhere because CRT interpolation is already
normalized. The only divisions are by 2 b = 4 cos(beta/2), the same real
constants the forward multiplied by.
"""
import numpy as np

N = 512
L = 9          # 2^9 = 512

# ---------------------------------------------------------------- tables ---
# Per level j (j = 0..L-2): parents are 2^j nodes of degree d = N/2^j.
# Child moduli are z^{d/2} + A z^{d/4} + C with per-node tables A1, C1 (upper
# child) and A2, C2 (lower child). BETA[j] carries each trinomial node's
# angle (NaN for the binomial node 0). The leaf table gives bin k per node.

BETA = [np.full(2**j, np.nan) for j in range(L)]
for j in range(L - 1):
    nb = BETA[j]; nx = BETA[j + 1]
    nx[1] = np.pi/2                       # z^{M/2} + 1 from the binomial node
    tri = ~np.isnan(nb)
    idx = np.nonzero(tri)[0]
    nx[2*idx]     = nb[idx]/2
    nx[2*idx + 1] = np.pi - nb[idx]/2

A1 = []; C1 = []; A2 = []; C2 = []
for j in range(L - 1):
    nb = BETA[j]; n = 2**j
    a1 = np.zeros(n); c1 = np.ones(n); a2 = np.zeros(n); c2 = np.ones(n)
    c1[0], c2[0] = -1.0, 1.0              # binomial split: z^{M/2} -+ 1
    tri = ~np.isnan(nb)
    a1[tri] = -2*np.cos(nb[tri]/2)
    a2[tri] =  2*np.cos(nb[tri]/2)
    A1.append(a1); C1.append(c1); A2.append(a2); C2.append(c2)

LEAF_BETA = BETA[L - 1]                                       # node m -> beta
LEAF_BIN  = np.zeros(2**(L - 1), dtype=int)
LEAF_BIN[1:] = np.rint(LEAF_BETA[1:]*N/(2*np.pi)).astype(int) # node m -> k
B_TAB = [2*np.cos(BETA[j + 1][2*np.arange(2**j)]) for j in range(L - 1)]
# B_TAB[j][p] = 2 cos(beta_p / 2) for trinomial parents (entry 0 unused)

# --------------------------------------------------------------- forward ---
def _fold(P, A, C):
    """Reduce parent residues P (n, 2d) mod z^d + A z^{d/2} + C per row."""
    c = P.copy(); d = P.shape[1]//2; h = d//2
    A = A[:, None]; C = C[:, None]
    u = c[:, d + h:2*d]
    c[:, d:d + h] -= A*u
    c[:, h:d]     -= C*u
    v = c[:, d:d + h]
    c[:, h:d]     -= A*v
    c[:, 0:h]     -= C*v
    return c[:, :d]

def bruun_rfft(x):
    X = np.asarray(x, dtype=np.float64).reshape(1, N)         # stage 0
    for j in range(L - 1):                                    # stages 1..8
        top = _fold(X, A1[j], C1[j])
        bot = _fold(X, A2[j], C2[j])
        d = X.shape[1]//2
        X = np.empty((2*X.shape[0], d))
        X[0::2] = top
        X[1::2] = bot
    out = np.zeros(N//2 + 1, dtype=np.complex128)
    out[0]    = X[0, 0] + X[0, 1]                             # z = +1
    out[N//2] = X[0, 0] - X[0, 1]                             # z = -1
    k = LEAF_BIN[1:]; beta = LEAF_BETA[1:]
    out[k] = X[1:, 0] + X[1:, 1]*np.exp(-1j*beta)
    return out

# --------------------------------------------------------------- inverse ---
def bruun_irfft(F):
    X = np.empty((2**(L - 1), 2))
    rA = F[0].real; rB = F[N//2].real
    X[0] = (rA + rB)/2, (rA - rB)/2                           # mod z^2 - 1
    k = LEAF_BIN[1:]; beta = LEAF_BETA[1:]
    r1 = -F[k].imag/np.sin(beta)
    X[1:, 1] = r1
    X[1:, 0] = F[k].real - r1*np.cos(beta)
    for j in range(L - 2, -1, -1):                            # CRT up-sweep
        R1 = X[0::2]; R2 = X[1::2]; h = X.shape[1]; dd = h//2
        n = 2**j
        C = np.empty((n, 2*h))
        # binomial parent (node 0)
        t0 = (R1[0] - R2[0])/2
        C[0, :h] = R1[0] - t0
        C[0, h:] = t0
        # trinomial parents (nodes 1..n-1), vectorized
        if n > 1:
            b = B_TAB[j][1:, None]
            dv = R2[1:] - R1[1:]
            traw = np.zeros((n - 1, h + dd))
            traw[:, dd:dd + h] += dv
            traw[:, 0:h]       += b*dv
            u = traw[:, h:h + dd]
            traw[:, h - dd:h] -= b*u
            traw[:, 0:dd]     -= u
            t = traw[:, :h]/(2*b)
            C[1:, :] = 0.0
            C[1:, 0:h]       += R1[1:] + t
            C[1:, dd:dd + h] -= b*t
            C[1:, h:2*h]     += t
        X = C
    return X[0]

# ------------------------------------------------------------ validation ---
if __name__ == "__main__":
    rng = np.random.default_rng(0)
    ef = eb = er = ei = 0.0
    for _ in range(50):
        x = rng.standard_normal(N)
        F = bruun_rfft(x)
        ef = max(ef, np.abs(F - np.fft.rfft(x)).max())
        eb = max(eb, np.abs(bruun_irfft(F) - x).max())
        er = max(er, np.abs(bruun_irfft(np.fft.rfft(x)) - x).max())
        ei = max(ei, np.abs(np.fft.irfft(bruun_rfft(x)) - x).max())
    print("bruun_rfft  vs np.fft.rfft        max abs err:", f"{ef:.2e}")
    print("bruun_irfft(bruun_rfft(x)) vs x   max abs err:", f"{eb:.2e}")
    print("bruun_irfft(np.fft.rfft(x)) vs x  max abs err:", f"{er:.2e}")
    print("np.fft.irfft(bruun_rfft(x)) vs x  max abs err:", f"{ei:.2e}")
