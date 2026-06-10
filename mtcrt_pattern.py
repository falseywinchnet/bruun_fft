#!/usr/bin/env python3
"""
mtcrt_pattern.py

Generator for the candidate "minimized-transport CRT" order found by the exact
small-N search.

The real power-of-two DFT atoms are:
    0      DC linear atom
    H      Nyquist linear atom
    k      quadratic conjugate-pair atom {k, N-k}, 1 <= k < N/2

Let M = N/2. The discovered recursive order T(M), up to reversal/conjugation
symmetries, is:

    T(2) = [0, H, 1]
    T(4) = [1, 2, 0, H, 3]

    for M >= 8:
        T(M) =
            middle_band(M/4 + 1 ... 3M/4)
          + low_band(1 ... M/4)
          + high_edge_map(T(M/4))

where high_edge_map keeps 0,H fixed and maps an interior atom j to:
        M - M/4 + j

Each interval band is internally split by plain balanced adjacent bisection.

Interpretation:
    The CRT first removes the transport-minimal middle conjugate band, then
    recursively closes the remaining high edge containing the DC/Nyquist seam.
    This avoids a large final traversal debt by making every split local in
    the circular root order.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union, Tuple


Atom = Union[int, str]


@dataclass
class Node:
    left: "Tree"
    right: "Tree"


Tree = Union[Atom, Node]


def tree_to_order(t: Tree) -> List[Atom]:
    if isinstance(t, Node):
        return tree_to_order(t.left) + tree_to_order(t.right)
    return [t]


def tree_to_string(t: Tree) -> str:
    if isinstance(t, Node):
        return f"({tree_to_string(t.left)},{tree_to_string(t.right)})"
    return str(t)


def balanced_interval_tree(lo: int, hi: int) -> Tree:
    """Balanced adjacent bisection tree for integer atoms lo..hi inclusive."""
    if lo > hi:
        raise ValueError("empty interval")
    if lo == hi:
        return lo
    n = hi - lo + 1
    mid = lo + n // 2 - 1
    return Node(balanced_interval_tree(lo, mid), balanced_interval_tree(mid + 1, hi))


def map_high_edge(t: Tree, M: int) -> Tree:
    """
    Map a smaller T(M/4) tree into the high edge of T(M).

    For M >= 8:
        smaller interior j -> M - M/4 + j
        0 and H stay at the global seam.
    """
    q = M // 4
    offset = M - q

    if isinstance(t, Node):
        return Node(map_high_edge(t.left, M), map_high_edge(t.right, M))

    if t == "0" or t == "H":
        return t

    return offset + int(t)


def mtcrt_tree_from_M(M: int) -> Tree:
    if M < 2 or (M & (M - 1)):
        raise ValueError("M=N/2 must be a power of two >= 2")

    if M == 2:
        return Node(Node("0", "H"), 1)

    if M == 4:
        return Node(Node(1, 2), Node(Node("0", "H"), 3))

    q = M // 4

    middle = balanced_interval_tree(q + 1, 3 * q)
    low = balanced_interval_tree(1, q)
    high = map_high_edge(mtcrt_tree_from_M(q), M)

    return Node(middle, Node(low, high))


def mtcrt_tree(N: int) -> Tree:
    if N < 4 or (N & (N - 1)):
        raise ValueError("N must be a power of two >= 4")
    return mtcrt_tree_from_M(N // 2)


def mtcrt_order(N: int) -> List[Atom]:
    return tree_to_order(mtcrt_tree(N))


def short_order(order: List[Atom], max_items: int = 40) -> str:
    if len(order) <= max_items:
        return " ".join(map(str, order))
    head = " ".join(map(str, order[:20]))
    tail = " ".join(map(str, order[-12:]))
    return f"{head} ... {tail}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("N", nargs="?", type=int, help="single transform size")
    ap.add_argument("--sizes", default="4,8,16,32,64,128,256,512,1024",
                    help="comma-separated sizes when N is omitted")
    ap.add_argument("--tree", action="store_true", help="print the full tree")
    args = ap.parse_args()

    if args.N:
        sizes = [args.N]
    else:
        sizes = [int(x) for x in args.sizes.split(",") if x.strip()]

    for N in sizes:
        t = mtcrt_tree(N)
        order = tree_to_order(t)
        print(f"N={N} atoms={len(order)}")
        print(f"order: {short_order(order)}")
        if args.tree:
            print(f"tree:  {tree_to_string(t)}")
        print()


if __name__ == "__main__":
    main()
