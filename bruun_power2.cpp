// bruun_power2.hpp-style single file
// Scalar Bruun real FFT / inverse real FFT for any power-of-two N >= 4.
//
// Shape:
//   - Forward input:  N real doubles
//   - Forward output: N/2 + 1 complex_t bins, NumPy/FFTW rfft convention
//   - Inverse input:  N/2 + 1 complex_t bins
//   - Inverse output: N real doubles
//
// Properties:
//   - All interior arithmetic is real.
//   - Forward works in place over one real work buffer.
//   - Inverse works in place over one real output/work buffer.
//   - One master table T[i] = 2 cos(pi i / N), i = 0..N-1.
//   - One reflected-Gray index table IDX[m], m = 0..N/2-1.
//   - One reciprocal table R[m] = 1 / T[IDX[m]] for inverse merges.
//   - Complex arithmetic appears only at final bin pack/unpack.
//
// Compile test:
//   g++ -O3 -march=native -std=c++17 -DBRUUN_POWER2_TEST_MAIN bruun_power2.cpp -lm -o bruun_power2_test

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <algorithm>
#include <random>
#include <stdexcept>

#if defined(_MSC_VER) && !defined(__clang__)
#define RESTRICT __restrict
#elif defined(__GNUC__)
#define RESTRICT __restrict__
#elif defined(__clang__)
#define RESTRICT __restrict__
#else
#define RESTRICT
#endif

#ifndef M_PI
#define M_PI 3.141592653589793238462643383279502884
#endif

struct complex_t {
    double re;
    double im;
};

static inline bool bruun_is_power_of_two(int n) {
    return n > 0 && ((n & (n - 1)) == 0);
}

static inline int bruun_ilog2_pow2(int n) {
    int l = 0;
    while (n > 1) {
        n >>= 1;
        ++l;
    }
    return l;
}

static inline int bruun_graydecode(int g) {
    for (int s = 1; s < 32; s <<= 1) {
        g ^= g >> s;
    }
    return g;
}

static inline int bruun_bitrev(int r, int t) {
    int out = 0;
    for (int i = 0; i < t; ++i) {
        out = (out << 1) | (r & 1);
        r >>= 1;
    }
    return out;
}

static inline int bruun_idx_runtime(int m, int L) {
#if defined(__GNUC__) || defined(__clang__)
    const int t = 31 - __builtin_clz((unsigned)m);
#else
    int t = 0;
    for (int x = m; x > 1; x >>= 1) ++t;
#endif
    const int r = m ^ (1 << t);
    return (2 * bruun_graydecode(bruun_bitrev(r, t)) + 1) << ((L - 2) - t);
}

class BruunRFFT {
public:
    explicit BruunRFFT(int n)
        : N(n), L(bruun_ilog2_pow2(n)), bins(n / 2 + 1), T(n), R(n / 2), IDX(n / 2)
    {
        if (!bruun_is_power_of_two(N) || N < 4) {
            throw std::invalid_argument("BruunRFFT requires power-of-two N >= 4");
        }

        for (int i = 0; i < N; ++i) {
            T[i] = 2.0 * std::cos(M_PI * double(i) / double(N));
        }

        IDX[0] = 0;
        R[0] = 0.0;

        for (int m = 1; m < N / 2; ++m) {
            IDX[m] = bruun_idx_runtime(m, L);
            R[m] = 1.0 / T[IDX[m]];
        }
    }

    int size() const { return N; }
    int bin_count() const { return bins; }

    const double* table_T() const { return T.data(); }
    const double* table_R() const { return R.data(); }
    const int* index_table() const { return IDX.data(); }

    void rfft(const double* RESTRICT input, complex_t* RESTRICT X, double* RESTRICT work) const {
        for (int i = 0; i < N; ++i) {
            work[i] = input[i];
        }

        rfft_inplace(work, X);
    }

    void rfft_inplace(double* RESTRICT v, complex_t* RESTRICT X) const {
        for (int jj = 0; jj < L - 1; ++jj) {
            const int s = N >> jj;
            const int h = s >> 1;

            for (int i = 0; i < h; ++i) {
                const double a = v[i];
                const double b = v[h + i];
                v[i] = a + b;
                v[h + i] = a - b;
            }

            for (int m = 1; m < (1 << jj); ++m) {
                const int o = m * s;
                const int q = s >> 2;
                const double b = T[IDX[m]];

                for (int n = 0; n < q; ++n) {
                    const double P0 = v[o + n];
                    const double P1 = v[o + q + n];
                    const double P2 = v[o + 2*q + n];
                    const double P3 = v[o + 3*q + n];

                    const double t1 = b * P3;
                    const double t2 = b * P2;
                    const double e = P0 - P2;
                    const double g = P1 - P3 + b * t1;

                    v[o + n]       = e - t1;
                    v[o + q + n]   = g + t2;
                    v[o + 2*q + n] = e + t1;
                    v[o + 3*q + n] = g - t2;
                }
            }
        }

        for (int k = 0; k < bins; ++k) {
            X[k].re = 0.0;
            X[k].im = 0.0;
        }

        X[0].re = v[0] + v[1];
        X[0].im = 0.0;
        X[N / 2].re = v[0] - v[1];
        X[N / 2].im = 0.0;

        const int quarter = N / 4;

        for (int m = 1; m < N / 2; ++m) {
            const int k = IDX[m];

            const double c = 0.5 * T[2 * k];
            const double s = 0.5 * T[2 * std::abs(quarter - k)];

            const double r0 = v[2*m];
            const double r1 = v[2*m + 1];

            X[k].re = r0 + r1 * c;
            X[k].im = -r1 * s;
        }
    }

    void irfft(const complex_t* RESTRICT X, double* RESTRICT output) const {
        irfft_inplace(X, output);
    }

    void irfft_inplace(const complex_t* RESTRICT X, double* RESTRICT v) const {
        v[0] = 0.5 * (X[0].re + X[N / 2].re);
        v[1] = 0.5 * (X[0].re - X[N / 2].re);

        const int quarter = N / 4;

        for (int m = 1; m < N / 2; ++m) {
            const int k = IDX[m];

            const double c = 0.5 * T[2 * k];
            const double s = 0.5 * T[2 * std::abs(quarter - k)];

            const double r1 = -X[k].im / s;
            v[2*m] = X[k].re - r1 * c;
            v[2*m + 1] = r1;
        }

        for (int jj = L - 2; jj >= 0; --jj) {
            const int s = N >> jj;
            const int h = s >> 1;

            for (int m = (1 << jj) - 1; m > 0; --m) {
                const int o = m * s;
                const int q = s >> 2;
                const double b = T[IDX[m]];
                const double rb = R[m];

                for (int n = 0; n < q; ++n) {
                    const double c0 = v[o + n];
                    const double c1 = v[o + q + n];
                    const double d0 = v[o + 2*q + n];
                    const double d1 = v[o + 3*q + n];

                    const double t1 = 0.5 * (d0 - c0);
                    const double t2 = 0.5 * (c1 - d1);
                    const double e  = 0.5 * (c0 + d0);
                    const double g  = 0.5 * (c1 + d1);

                    const double P3 = t1 * rb;
                    const double P2 = t2 * rb;
                    const double P1 = g + P3 - b * t1;
                    const double P0 = e + P2;

                    v[o + n]       = P0;
                    v[o + q + n]   = P1;
                    v[o + 2*q + n] = P2;
                    v[o + 3*q + n] = P3;
                }
            }

            for (int i = 0; i < h; ++i) {
                const double a = v[i];
                const double b = v[h + i];
                v[i] = 0.5 * (a + b);
                v[h + i] = 0.5 * (a - b);
            }
        }
    }

private:
    int N;
    int L;
    int bins;
    std::vector<double> T;
    std::vector<double> R;
    std::vector<int> IDX;
};

#ifdef BRUUN_POWER2_TEST_MAIN

static double max_abs_real(const double* a, const double* b, int n) {
    double e = 0.0;
    for (int i = 0; i < n; ++i) {
        e = std::max(e, std::abs(a[i] - b[i]));
    }
    return e;
}

static void direct_rfft(const double* x, complex_t* X, int N) {
    for (int k = 0; k <= N / 2; ++k) {
        double re = 0.0;
        double im = 0.0;

        for (int n = 0; n < N; ++n) {
            const double a = -2.0 * M_PI * double(k) * double(n) / double(N);
            re += x[n] * std::cos(a);
            im += x[n] * std::sin(a);
        }

        X[k].re = re;
        X[k].im = im;
    }
}

static double max_abs_complex(const complex_t* a, const complex_t* b, int n) {
    double e = 0.0;
    for (int i = 0; i < n; ++i) {
        const double dr = a[i].re - b[i].re;
        const double di = a[i].im - b[i].im;
        e = std::max(e, std::sqrt(dr*dr + di*di));
    }
    return e;
}

int main() {
    std::mt19937_64 rng(0);
    std::uniform_real_distribution<double> dist(-1.0, 1.0);

    const int sizes[] = {4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096};

    for (int N : sizes) {
        BruunRFFT fft(N);

        std::vector<double> x(N), y(N), work(N);
        std::vector<complex_t> X(N / 2 + 1), D(N / 2 + 1);

        double worst_roundtrip = 0.0;
        double worst_direct = 0.0;

        const int trials = (N <= 256) ? 50 : 10;

        for (int trial = 0; trial < trials; ++trial) {
            for (int i = 0; i < N; ++i) {
                x[i] = dist(rng);
            }

            fft.rfft(x.data(), X.data(), work.data());
            fft.irfft(X.data(), y.data());

            worst_roundtrip = std::max(worst_roundtrip, max_abs_real(x.data(), y.data(), N));

            if (N <= 1024) {
                direct_rfft(x.data(), D.data(), N);
                worst_direct = std::max(worst_direct, max_abs_complex(X.data(), D.data(), N / 2 + 1));
            }
        }

        std::printf("N=%5d  direct_err=%10.3e  roundtrip_err=%10.3e\n", N, worst_direct, worst_roundtrip);
    }

    return 0;
}

#endif
