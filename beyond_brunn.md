# The Bruun Mission: How a Forgotten FFT method Became a Competitive Transform

## 1. The Starting Bet

The project began with a simple suspicion: Bruun’s 1978 paper was a signpost to a different FFT world.

The standard FFT tradition usually begins with complex roots of unity, twiddle factors, bit reversal, and butterfly networks. Bruun began elsewhere: with z-transform filters, zero configurations, and real-coefficient filter trees. That difference mattered. It suggested that the DFT could be reached not only by rotating complex numbers, but by factoring polynomials over the real numbers and walking a tree of quotient rings.

What if Bruun was seriously onto something? What if the most optimal FFT we have today.. could be more optimal?

That question drove us to collect the files in this repo and to try many times, failing, to implement it.

Then it sat. it waited for AGI to come along.  For 2 years.

## 2. First Reconstruction: Bruun as a Polynomial Remainder Tree

The first working reconstruction treated a real input signal as a polynomial:

```text
x0 + x1 z + x2 z² + ... + x(N-1) z^(N-1)
```

The DFT is evaluation of that polynomial at roots of unity. Bruun’s method reaches those evaluations by recursively reducing the polynomial modulo real factors of `z^N - 1`.

Instead of splitting immediately into complex roots, the tree keeps conjugate roots paired. That produces real quadratic factors:

```text
z² - b z + 1
```

where `b = 2 cos(theta)`.

The forward Bruun transform became a staged remainder computation. Each level reduces a parent polynomial into two child remainders. At the bottom, each leaf remainder is degree one:

```text
r0 + r1 z
```

Those two real numbers contain the same information as one conjugate FFT bin pair.

This was the first reframing: Brune is CRT decomposition of the DFT polynomial.

## 3. The Inverse: CRT, Not a Reverse FFT Trick

The first demonstration Claude Fable offered of pure superhuman prowess was the inverse.

The forward transform maps one polynomial into many remainders. Algebraically, that is a Chinese remainder theorem map. Therefore the inverse is not guessed by reversing butterflies. It is CRT reconstruction.

For the binomial branches, the merge is simple averaging. For the trinomial branches, the sibling factors have enough structure to derive a closed-form reconstruction. That gave an exact inverse transform.

## 4. The Coefficient Discovery: One Ladder, Not Many Twiddles

We insisted that further optimization was possible after visually inspecting the twiddles and seeing the intrinsic dance they did.

We asked for more work.

The next discovery was that the apparent mess of Bruun coefficients was not actually messy.

The tree coefficients follow a reflected Gray/bit-reversal pattern. Every coefficient and every leaf bin can be indexed from one master table:

```text
T[i] = 2 cos(pi i / N)
```

A node `m` maps to an integer `IDX[m]`, and that single integer names:

1. the node’s fold coefficient,
2. the output bin corresponding to the leaf,
3. the local angle used at the bottom.

This collapsed the transform’s coefficient system into one real cosine ladder.

That was different from ordinary FFT twiddle tables. Cooley-Tukey twiddles appear as stagewise angular combs. Bruun’s coefficients appeared “dithered” in tree order, but when sorted they formed one clean cosine/sigmoid-like ladder, much like a rearranged Cooley-Tukey twiddle we happen to be familiar with.

## 5. The Monomial Kernel and Its Limit

The first serious C++ implementation used the monomial basis at each quadratic leaf:

```text
r0 + r1 z
```

The core trinomial fold acted on four quarters of a block:

```text
P0, P1, P2, P3
```

and required three real multiplications per quartet:

```text
b*P2
b*P3
(b² - 1)*P3
```

This form was compact, all-real, and in-place. It immediately beat a naive complex Cooley-Tukey wrapper. But it did not beat FFTW.

Several attempted reductions failed for good reasons. Scalar rescaling did not remove a multiplication; it moved the cost. Tangent-FFT-style tricks did not transfer cleanly, because in Bruun’s trinomial quotient, multiplication by `z` is not a free signed shift. It folds through the coefficient `b`.

That failure was useful. It showed that the monomial basis was probably near a local arithmetic minimum.

This was the fourth reframing: the obvious Bruun basis is valid but not natural.

## 6. Bruun-Order Residues: The Complex Spectrum Was Optional

The next discovery came from convolution.

At the leaves, Bruun naturally produces residue pairs. In the monomial basis, each nontrivial leaf lives in:

```text
R[z] / (z² - b z + 1)
```

For standard FFT output, those residues are converted into complex bins by evaluating at a complex root. But for convolution, that conversion is unnecessary.

Circular convolution is multiplication in:

```text
R[z] / (z^N - 1)
```

The CRT says that this multiplication decomposes into independent multiplications inside each tiny quotient ring. Therefore, for convolution, the complex FFT chart is just overhead.

Instead of:

```text
real signal -> complex bins -> complex multiply -> inverse FFT
```

one can do:

```text
real signal -> Bruun leaf residues -> real quotient multiply -> CRT merge
```

## 7. The Normalized Basis: Making Each Leaf Locally Complex

The deepest math-side improvement was the normalized leaf basis.

Instead of representing each quadratic residue as:

```text
r0 + r1 z
```

we changed basis inside each quadratic quotient to:

```text
r0 + r1 e
```

where:

```text
e = (z - cos(alpha)) / sin(alpha)
```

Inside the quotient:

```text
z² - 2 cos(alpha) z + 1 = 0
```

this gives:

```text
e² = -1
```

That transformed every nontrivial Bruun leaf into a local complex plane.

The payoff was immediate.

In the monomial basis, converting a leaf to a complex FFT bin costs cosine/sine multiplications:

```text
X[k].re = r0 + c*r1
X[k].im = -s*r1
```

In the normalized basis, the conversion is free:

```text
X[k].re = r0
X[k].im = -r1
```

The inverse also became cleaner. The old monomial inverse needed reciprocal coefficients. The normalized inverse became an inverse plane rotation.

This changed the Bruun transform from “real remainder tree plus leaf evaluation” into “real tree of local complex coordinates.”

This was the sixth reframing: the right Bruun basis is not monomial. It is normalized so every quadratic quotient has its own imaginary unit.

## 8. The Memory Problem: Passes, Not Just Multiplies

Once the arithmetic was under control, the main enemy became memory movement.

The breadth-first staged Bruun transform touched the whole work array at every level. That is simple, but expensive. FFTW wins much of its speed by keeping subproblems hot in cache and using generated codelets.

The Bruun tree has the same opportunity. A depth-first traversal processes a block, recursively processes its children, and keeps smaller subtrees resident in cache. This changes the practical character of the algorithm without changing the mathematics.

The initial fused-tail codelets removed the last few full-array passes. Then the depth-first formulation extended that idea upward: once a block enters cache, finish more of its subtree before moving on.

This was the seventh reframing: Bruun is naturally recursive, and breadth-first stages were an implementation crutch.

## 9. The Output Scatter Problem

Even after depth-first traversal, one problem remained: standard FFT output order.

Bruun’s natural leaves do not arrive in increasing frequency order. Writing each final bin directly to `X[k]` causes scattered stores. For small and mid-size transforms, fused scatter is fine because it avoids an extra pass. For large transforms, scattered stores become expensive.

Fable's two-phase pack option changed the tradeoff:

1. produce residues in Bruun/block order,
2. perform a separate pass that writes output bins sequentially.

That means scattered reads but streaming writes. On Apple Silicon, this changed the large-N behavior dramatically.


## 10. The Consumer-Safe SIMD Decision

The project deliberately avoided making “go wider” the central story.

The final Apple Silicon result used 128-bit NEON, not AVX-512 and not a server-only vector strategy. The same design maps naturally to SSE2-style two-double vectors on x86. 

## 11. The One-File Result

The final working artifact became a single C++ file implementing a normalized-basis, power-of-two, real-to-complex Bruun RFFT with a built-in FFTW comparison harness.

The file supports:

```text
real -> complex forward
complex -> real inverse
power-of-two sizes
consumer-safe 128-bit SIMD
optional wider SIMD
fused-scatter pack
two-phase pack
FFTW comparison
roundtrip validation
```

On Apple Silicon, fused-scatter pack beat FFTW from 512 through 16384. Two-phase pack then made large sizes competitive or faster, including wins at 65536, 131072, and 262144 in the observed run.

The final result is a single-file implementation challenging FFTW on real measurements.

Bruun’s version is young. Some remaining obvious directions are:

```text
automatic pack-mode selection by size
better large-N blocking
cleaner depth-first scheduling
separate consumer 128-bit and server AVX2/AVX-512 backends
inverse fusion
convolution API in normalized Bruun residues
GPU/shared-memory experiments
```
A less than obvious way to use bruun more optimally is to call forward to residue->
use a residue-converted filter diagonal/pointwise in frequency: convolution, fixed FIR filtering by FFT, spectral gain/EQ, power spectrum, Wiener-like filters, deconvolution with precomputed inverse response, etc. 

real input
-> real Bruun transform
-> real-pair spectral multiply
-> real Bruun inverse
-> real output

All happens in realspace. none happens in complex space.

bruun_fastplan_benchmark_standard.cpp

Bruun transform itself is much faster.
Standard FFT bin order costs a full permutation pass.
Even after that pass, Bruun is still faster.
If the downstream operation can stay in Bruun order, the permutation tax disappears.

Filtering is the perfect case. A convolution/filtering pipeline can be:

input -> Bruun native spectrum
filter -> Bruun native spectrum, precomputed once
pointwise multiply in Bruun order
inverse

No standard bin order needed in the hot path.

note: sink is just a random val used to make sure things return
err is bruun to fftw, rt is round trip

```text

       N    iters     FFTW_ns   Native_ns      Std_ns      N/F      S/F  checks
     512    39062       713.0       420.3       530.4    0.589    0.744  err 1.9e-14 rt 6.7e-16 sink 65824.142
    1024    17578      1227.8       865.9      1039.4    0.705    0.847  err 3.7e-14 rt 7.8e-16 sink -5468.4407
    2048     7990      2598.3      1899.2      2284.6    0.731    0.879  err 1.2e-13 rt 8.9e-16 sink 14144.015
    4096     3662      7062.4      3991.2      5657.4    0.565    0.801  err 2.7e-13 rt 8.9e-16 sink 3350.7713
    8192     1690     14654.4     10851.1     13591.5    0.740    0.927  err 6.6e-13 rt 8.9e-16 sink 4629.461
    16384      784     38772.7     23404.3     34286.4    0.604    0.884  err 1.6e-12 rt 1.1e-15 sink 5185.7736
    32768      366    140854.4     46239.8     94665.9    0.328    0.672  err 7.1e-12 rt 1.1e-15 sink 1821.2476
    65536      171    289400.3     97985.4    198457.1    0.339    0.686  err 3.1e-11 rt 1.2e-15 sink -2434.4398
    131072       80    586522.4    216257.8    432775.0    0.369    0.738  err 6.4e-11 rt 1.1e-15 sink -876.38164
    262144       38   1249189.7    461496.7    884805.9    0.369    0.708  err 1.6e-10 rt 1.4e-15 sink 1037.4371
    524288       18   3719287.1   1061650.4   1969548.6    0.285    0.530  err 5.0e-10 rt 1.4e-15 sink 1943.0637
    1048576       16   5568333.4   2339651.1   4224322.9    0.420    0.759  err 2.6e-09 rt 1.4e-15 sink 2260.0734
    2097152       16  15123197.9   5356031.2   9845861.9    0.354    0.651  err 5.8e-09 rt 1.6e-15 sink -157.32364
    4194304       16  32056914.1  10711273.4  21024421.9    0.334    0.656  err 1.2e-08 rt 1.6e-15 sink -1799.7265
    8388608       16  67964679.7  24610052.1  45509359.4    0.362    0.670  err 5.5e-08 rt 1.7e-15 sink -7513.5165
    16777216       16 149024489.6  48852486.9  91471885.4    0.328    0.614  err 1.8e-07 rt 1.8e-15 sink 9833.6094
    33554432       16 324168343.8 107310903.6 187875562.5    0.331    0.580  err 5.3e-07 rt 1.8e-15 sink 14054.638
    67108864       16 726628489.6 235320187.5 437079622.4    0.324    0.602  err 7.1e-07 rt 1.8e-15 sink -30098.821

```

My intention beyond this point is to develop an optimal FFT using an optimal CRT -see the conversation traces ChatGPT-Model Intelligence in DSP.md

## 14. Bruun in One Sentence

A forgotten FFT approach that was a mere curiosity to a handful of mathematicians was rebuilt as a CRT transform, given an exact inverse, re-indexed through one coefficient ladder, moved into a normalized local-complex basis, reorganized around cache and output policy, and brought into direct competition with FFTW in a single-file implementation.

Anthropic did NOT contribute free credits to this effort and can suck my PEEN.
