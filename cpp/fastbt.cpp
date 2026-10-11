// fastbt: C++ backtest core for Kairos, exposed to Python with pybind11.
//
//   strat_returns(close, pos, cost_bps) -> daily strategy returns
//   ma_grid(close, fasts, slows, cost_bps, split, allow_short) -> (IS Sharpe, OOS Sharpe)
//
// Conventions match api/quant.py exactly: pos[t] is decided at the close of day t
// and held over day t+1, costs are charged on turnover, Sharpe uses ddof=1 and 252 days.
// Build: ./build_cpp.sh

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace py = pybind11;
using namespace std;

using CArray = py::array_t<double, py::array::c_style | py::array::forcecast>;

static const double kNaN = numeric_limits<double>::quiet_NaN();

static double sharpe_of(const double* r, size_t n) {
    if (n < 3) return 0.0;
    double m = 0.0;
    for (size_t i = 0; i < n; ++i) m += r[i];
    m /= static_cast<double>(n);
    double v = 0.0;
    for (size_t i = 0; i < n; ++i) {
        double d = r[i] - m;
        v += d * d;
    }
    v /= static_cast<double>(n - 1);
    if (v <= 0.0) return 0.0;
    return m / sqrt(v) * sqrt(252.0);
}

static vector<double> to_vec(const CArray& a) {
    auto u = a.unchecked<1>();
    vector<double> v(static_cast<size_t>(u.shape(0)));
    for (ssize_t i = 0; i < u.shape(0); ++i) v[static_cast<size_t>(i)] = u(i);
    return v;
}

py::array_t<double> strat_returns(const CArray& close, const CArray& pos, double cost_bps) {
    vector<double> c = to_vec(close), p = to_vec(pos);
    const size_t n = c.size();
    if (p.size() != n) throw invalid_argument("close and pos must have the same length");
    py::array_t<double> out(static_cast<ssize_t>(n));
    auto o = out.mutable_unchecked<1>();
    {
        py::gil_scoped_release release;
        const double cost = cost_bps / 1e4;
        double prev_held = 0.0;
        if (n > 0) o(0) = 0.0;
        for (size_t t = 1; t < n; ++t) {
            double held = p[t - 1];
            double r = c[t] / c[t - 1] - 1.0;
            o(static_cast<ssize_t>(t)) = held * r - fabs(held - prev_held) * cost;
            prev_held = held;
        }
    }
    return out;
}

py::tuple ma_grid(const CArray& close, const vector<int>& fasts, const vector<int>& slows,
                  double cost_bps, int split, bool allow_short) {
    vector<double> px = to_vec(close);
    const size_t n = px.size();
    const size_t nx = fasts.size(), ny = slows.size();
    if (split < 0 || static_cast<size_t>(split) > n) throw invalid_argument("split out of range");

    py::array_t<double> g_is({static_cast<ssize_t>(ny), static_cast<ssize_t>(nx)});
    py::array_t<double> g_oos({static_cast<ssize_t>(ny), static_cast<ssize_t>(nx)});
    auto gi = g_is.mutable_unchecked<2>();
    auto go = g_oos.mutable_unchecked<2>();

    {
        py::gil_scoped_release release;

        vector<double> pre(n + 1, 0.0);
        for (size_t i = 0; i < n; ++i) pre[i + 1] = pre[i] + px[i];
        vector<double> ret(n, 0.0);
        for (size_t t = 1; t < n; ++t) ret[t] = px[t] / px[t - 1] - 1.0;

        // one SMA per distinct window, computed once from the prefix sums
        unordered_map<int, vector<double>> cache;
        auto sma = [&](int w) -> const vector<double>& {
            auto it = cache.find(w);
            if (it != cache.end()) return it->second;
            vector<double> s(n, kNaN);
            if (w >= 1)
                for (size_t t = static_cast<size_t>(w) - 1; t < n; ++t)
                    s[t] = (pre[t + 1] - pre[t + 1 - static_cast<size_t>(w)]) / w;
            return cache.emplace(w, move(s)).first->second;
        };

        const double lo = allow_short ? -1.0 : 0.0;
        const double cost = cost_bps / 1e4;
        vector<double> sr(n, 0.0);

        for (size_t yi = 0; yi < ny; ++yi) {
            for (size_t xi = 0; xi < nx; ++xi) {
                const int f = fasts[xi], s = slows[yi];
                if (f >= s || f < 1) {
                    gi(yi, xi) = kNaN;
                    go(yi, xi) = kNaN;
                    continue;
                }
                const vector<double>& a = sma(f);
                const vector<double>& b = sma(s);
                const size_t first = static_cast<size_t>(s) - 1;  // both SMAs valid from here
                auto position = [&](size_t t) -> double {
                    if (t < first) return 0.0;
                    return a[t] > b[t] ? 1.0 : lo;
                };
                double prev_held = 0.0;
                sr[0] = 0.0;
                for (size_t t = 1; t < n; ++t) {
                    double held = position(t - 1);
                    sr[t] = held * ret[t] - fabs(held - prev_held) * cost;
                    prev_held = held;
                }
                gi(yi, xi) = sharpe_of(sr.data(), static_cast<size_t>(split));
                go(yi, xi) = sharpe_of(sr.data() + split, n - static_cast<size_t>(split));
            }
        }
    }
    return py::make_tuple(g_is, g_oos);
}

PYBIND11_MODULE(fastbt, m) {
    m.doc() = "Kairos C++ backtest core";
    m.def("strat_returns", &strat_returns, py::arg("close"), py::arg("pos"), py::arg("cost_bps") = 0.0,
          "Daily strategy returns for a position series (held[t] = pos[t-1]).");
    m.def("ma_grid", &ma_grid, py::arg("close"), py::arg("fasts"), py::arg("slows"),
          py::arg("cost_bps") = 0.0, py::arg("split"), py::arg("allow_short") = false,
          "In-sample and out-of-sample Sharpe for every (fast, slow) SMA pair.");
    m.attr("__version__") = "1.0";
}
