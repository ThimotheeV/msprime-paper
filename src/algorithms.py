"""
Python versions of the algorithms from the paper.
"""
from __future__ import print_function
from __future__ import division

import random
import argparse

import bintrees
import msprime
import numpy as np
import statsmodels.api as sm
import matplotlib

# Force matplotlib to not use any Xwindows backend.
matplotlib.use('Agg')
from matplotlib import pyplot


class FenwickTree(object):
    """
    A Fenwick Tree to represent cumulative frequency tables over
    integers. Each index from 1 to max_index initially has a
    zero frequency.

    This is an implementation of the Fenwick tree (also known as a Binary
    Indexed Tree) based on "A new data structure for cumulative frequency
    tables", Software Practice and Experience, Vol 24, No 3, pp 327 336 Mar
    1994. This implementation supports any non-negative frequencies, and the
    search procedure always returns the smallest index such that its cumulative
    frequency <= f. This search procedure is a slightly modified version of
    that presented in Tech Report 110, "A new data structure for cumulative
    frequency tables: an improved frequency-to-symbol algorithm." available at
    https://www.cs.auckland.ac.nz/~peter-f/FTPfiles/TechRep110.ps
    """
    def __init__(self, max_index):
        assert max_index > 0
        self.__max_index = max_index
        self.__tree = [0 for j in range(max_index + 1)]
        # Compute the binary logarithm of max_index
        u = self.__max_index
        while u != 0:
            self.__log_max_index = u
            u -= (u & -u)

    def get_total(self):
        """
        Returns the total cumulative frequency over all indexes.
        """
        return self.get_cumulative_frequency(self.__max_index)

    def increment(self, index, v):
        """
        Increments the frequency of the specified index by the specified
        value.
        """
        assert 0 < index <= self.__max_index
        j = index
        while j <= self.__max_index:
            self.__tree[j] += v
            j += (j & -j)

    def set_value(self, index, v):
        """
        Sets the frequency at the specified index to the specified value.
        """
        f = self.get_frequency(index)
        self.increment(index, v - f)

    def get_cumulative_frequency(self, index):
        """
        Returns the cumulative frequency of the specified index.
        """
        assert 0 < index <= self.__max_index
        j = index
        s = 0
        while j > 0:
            s += self.__tree[j]
            j -= (j & -j)
        return s

    def get_frequency(self, index):
        """
        Returns the frequency of the specified index.
        """
        assert 0 < index <= self.__max_index
        j = index
        v = self.__tree[j]
        p = j & (j - 1)
        j -= 1
        while p != j:
            v -= self.__tree[j]
            j = j & (j - 1)
        return v

    def find(self, v):
        """
        Returns the smallest index with cumulative sum >= v.
        """
        j = 0
        s = v
        half = self.__log_max_index
        while half > 0:
            # Skip non-existant entries
            while j + half > self.__max_index:
                half >>= 1
            k = j + half
            if s > self.__tree[k]:
                j = k
                s -= self.__tree[j]
            half >>= 1
        return j + 1


class Segment(object):
    """
    A class representing a single segment. Each segment has a left
    and right, denoting the loci over which it spans, a node and a
    next, giving the next in the chain.
    """
    def __init__(self, index):
        self.left = None
        self.right = None
        self.node = None
        self.prev = None
        self.next = None
        self.index = index

    def __str__(self):
        s = "({0}:{1}-{2}->{3}: prev={4} next={5})".format(
            self.index, self.left, self.right, self.node, repr(self.prev),
            repr(self.next))
        return s


class Simulator(object):
    """
    A reference implementation of the multi locus simulation algorithm.
    """
    def __init__(self, n, m, r, max_segments=100):
        self.n = n
        self.m = m
        self.r = r
        self.max_segments = max_segments
        self.segment_stack = []
        self.segments = [None for j in range(self.max_segments + 1)]
        for j in range(self.max_segments):
            s = Segment(j + 1)
            self.segments[j + 1] = s
            self.segment_stack.append(s)
        # We'd like to use an AVLTree here for P but the API doesn't quite
        # do what we need. Lists are inefficient here and should not be
        # used in a real implementation.
        self.P = [None for j in range(n)]
        self.C = []
        self.L = FenwickTree(self.max_segments)
        self.S = bintrees.AVLTree()
        for j in range(n):
            x = self.alloc_segment(0, m, j + 1)
            self.L.set_value(x.index, m - 1)
            self.P[j] = x
        self.S[0] = n
        self.S[m] = -1
        self.t = 0
        self.w = n + 1
        self.num_ca_events = 0
        self.num_re_events = 0

    def alloc_segment(self, left, right, node, prev=None, next=None):
        """
        Pops a new segment off the stack and sets its properties.
        """
        s = self.segment_stack.pop()
        s.left = left
        s.right = right
        s.node = node
        s.next = next
        s.prev = prev
        return s

    def free_segment(self, u):
        """
        Frees the specified segment making it ready for reuse and
        setting its weight to zero.
        """
        self.L.set_value(u.index, 0)
        self.segment_stack.append(u)

    def simulate(self):
        """
        Simulates the algorithm until all loci have coalesced.
        """
        while len(self.P) != 0:
            # self.print_state()
            # self.verify()
            lambda_r = self.r * self.L.get_total()
            lambda_all = lambda_r + len(self.P) * (len(self.P) - 1)
            self.t += random.expovariate(lambda_all)
            if random.random() < lambda_r / lambda_all:
                self.recombination_event()
            else:
                self.common_ancestor_event()

    def recombination_event(self):
        """
        Implements a recombination event.
        """
        self.num_re_events += 1
        h = random.randint(1, self.L.get_total())
        # Get the segment containing the h'th link
        y = self.segments[self.L.find(h)]
        k = y.right - self.L.get_cumulative_frequency(y.index) + h - 1
        x = y.prev
        if y.left < k:
            # Make new segment
            z = self.alloc_segment(k, y.right, y.node, None, y.next)
            if y.next is not None:
                y.next.prev = z
            y.next = None
            y.right = k
            self.L.increment(y.index, k - z.right)
        else:
            # split the link between x and y.
            x.next = None
            y.prev = None
            z = y
        self.L.set_value(z.index, z.right - z.left - 1)
        self.P.append(z)

    def common_ancestor_event(self):
        """
        Implements a coancestry event.
        """
        self.num_ca_events += 1
        # Choose two ancestors uniformly.
        j = random.randint(0, len(self.P) - 1)
        x = self.P[j]
        del self.P[j]
        j = random.randint(0, len(self.P) - 1)
        y = self.P[j]
        del self.P[j]
        z = None
        coalescence = False
        defrag_required = False

        while x is not None or y is not None:
            alpha = None
            if x is None or y is None:
                if x is not None:
                    alpha = x
                    x = None
                if y is not None:
                    alpha = y
                    y = None
            else:
                if y.left < x.left:
                    beta = x
                    x = y
                    y = beta
                if x.right <= y.left:
                    alpha = x
                    x = x.next
                    alpha.next = None
                elif x.left != y.left:
                    alpha = self.alloc_segment(x.left, y.left, x.node)
                    x.left = y.left
                else:
                    if not coalescence:
                        coalescence = True
                        self.w += 1
                    u = self.w - 1
                    # Put in breakpoints for the outer edges of the coalesced
                    # segment
                    l = x.left
                    r_max = min(x.right, y.right)
                    if l not in self.S:
                        j = self.S.floor_key(l)
                        self.S[l] = self.S[j]
                    if r_max not in self.S:
                        j = self.S.floor_key(r_max)
                        self.S[r_max] = self.S[j]
                    # Update the number of extant segments.
                    if self.S[l] == 2:
                        self.S[l] = 0
                        r = self.S.succ_key(l)
                    else:
                        r = l
                        while r < r_max and self.S[r] != 2:
                            self.S[r] -= 1
                            r = self.S.succ_key(r)
                        alpha = self.alloc_segment(l, r, u)
                    self.C.append((l, r, x.node, y.node, u, self.t))
                    # Now trim the ends of x and y to the right sizes.
                    if x.right == r:
                        self.free_segment(x)
                        x = x.next
                    else:
                        x.left = r
                    if y.right == r:
                        self.free_segment(y)
                        y = y.next
                    else:
                        y.left = r

            # loop tail; update alpha and integrate it into the state.
            if alpha is not None:
                if z is None:
                    self.P.append(alpha)
                    self.L.set_value(alpha.index, alpha.right - alpha.left - 1)
                else:
                    defrag_required |= (
                        z.right == alpha.left and z.node == alpha.node)
                    z.next = alpha
                    self.L.set_value(alpha.index, alpha.right - z.right)
                alpha.prev = z
                z = alpha

        if defrag_required:
            y = z
            while y.prev is not None:
                x = y.prev
                if x.right == y.left and x.node == y.node:
                    x.right = y.right
                    x.next = y.next
                    if y.next is not None:
                        y.next.prev = x
                    self.L.increment(x.index, y.right - y.left)
                    self.free_segment(y)
                y = x
        if coalescence:
            # Defrag the breakpoints set
            j = 0
            k = 0
            while k < self.m:
                k = self.S.succ_key(j)
                if self.S[j] == self.S[k]:
                    del self.S[k]
                else:
                    j = k

    def print_state(self):
        print("State @ time ", self.t)
        print("Links = ", self.L.get_total())
        print("Population:", len(self.P))
        for u in self.P:
            s = ""
            while u is not None:
                s += "({0}-{1}->{2}({3}))".format(
                    u.left, u.right, u.node, u.index)
                u = u.next
            print("\t" + s)
        print("Overlap counts", len(self.S))
        for k, x in self.S.items():
            print("\t", k, "\t:\t", x)
        print("Fenwick tree:", self.L.get_total())
        for j in range(1, self.max_segments + 1):
            s = self.L.get_frequency(j)
            if s != 0:
                print(
                    "\t", j, "->", s, self.L.get_cumulative_frequency(j))
        print("Coalescence records: ")
        for rec in self.C:
            print("\t", rec)
        self.verify()

    def verify(self):
        """
        Checks that the state of the simulator is consistent.
        """
        q = 0
        for u in self.P:
            assert u.prev is None
            left = u.left
            right = u.left
            while u is not None:
                assert u.left <= u.right
                if u.prev is not None:
                    s = u.right - u.prev.right
                else:
                    s = u.right - u.left - 1
                assert s == self.L.get_frequency(u.index)
                right = u.right
                v = u.next
                if v is not None:
                    assert v.prev == u
                u = v
            q += right - left - 1
        assert q == self.L.get_total()

        assert self.S[self.m] == -1
        # Check the ancestry tracking.
        A = bintrees.AVLTree()
        A[0] = 0
        A[self.m] = -1
        for u in self.P:
            while u is not None:
                if u.left not in A:
                    k = A.floor_key(u.left)
                    A[u.left] = A[k]
                if u.right not in A:
                    k = A.floor_key(u.right)
                    A[u.right] = A[k]
                k = u.left
                while k < u.right:
                    A[k] += 1
                    k = A.succ_key(k)
                u = u.next
        # Now, defrag A
        j = 0
        k = 0
        while k < self.m:
            k = A.succ_key(j)
            if A[j] == A[k]:
                del A[k]
            else:
                j = k
        assert list(A.items()) == list(self.S.items())

    def verify_end(self):
        """
        Verify the state of the simulation at the end.
        """
        # Check the coalescence records to make sure they correctly cover
        # space
        left_coords = sorted(set(r[0] for r in self.C))
        for k in left_coords:
            c = 0
            for l, r, _, _, _, _ in self.C:
                if l <= k < r:
                    c += 1
            assert c == self.n - 1


def generate_trees(l, r, u, c, t):
    """
    Algorithm T. Sequentially visits all trees in the specified
    tree sequence.
    """
    # Calculate the index vectors
    M = len(l)
    I = sorted(range(M), key=lambda j: (l[j], t[j]))
    O = sorted(range(M), key=lambda j: (r[j], -t[j]))
    pi = [0 for j in range(max(u) + 1)]
    j = 0
    k = 0
    while j < M:
        x = l[I[j]]
        while r[O[k]] == x:
            h = O[k]
            pi[c[h][0]] = pi[c[h][1]] = 0
            k = k + 1
        while j < M and l[I[j]] == x:
            h = I[j]
            pi[c[h][0]] = pi[c[h][1]] = u[h]
            j += 1
        yield pi


def count_leaves(l, r, u, c, t, S):
    """
    Algorithm L. Sequentially visits all trees in the specified
    tree sequence and maintain a count of the leaf nodes in the
    specified set for each node.
    """
    # Calculate the index vectors
    M = len(l)
    I = sorted(range(M), key=lambda j: (l[j], t[j]))
    O = sorted(range(M), key=lambda j: (r[j], -t[j]))
    pi = [0 for j in range(max(u) + 1)]
    beta = [0 for j in range(max(u) + 1)]
    for j in S:
        beta[j] = 1
    j = 0
    k = 0
    while j < M:
        x = l[I[j]]
        while r[O[k]] == x:
            h = O[k]
            pi[c[h][0]] = pi[c[h][1]] = 0
            b = beta[c[h][0]] + beta[c[h][1]]
            k += 1
            v = u[h]
            while v != 0:
                beta[v] -= b
                v = pi[v]
        while j < M and l[I[j]] == x:
            h = I[j]
            pi[c[h][0]] = pi[c[h][1]] = u[h]
            b = beta[c[h][0]] + beta[c[h][1]]
            j = j + 1
            v = u[h]
            while v != 0:
                beta[v] += b
                v = pi[v]
        yield pi, beta

def run_trees(args):
    tree_sequence = msprime.load(args.history_file)
    N = tree_sequence.get_num_nodes()
    records = list(tree_sequence.records())
    l = [record[0] for record in records]
    r = [record[1] for record in records]
    u = [record[2] for record in records]
    c = [record[3] for record in records]
    t = [record[4] for record in records]
    local_trees = []
    print("Trees:")
    for pi in generate_trees(l, r, u, c, t):
        local_trees.append(list(pi))
        print("\t", pi)
    local_counts = []
    S = set(range(1, tree_sequence.get_sample_size() + 1))
    print("Counts:")
    for pi, beta in count_leaves(l, r, u, c, t, S):
        local_counts.append(list(beta))
        print("\t", beta)
    msp_trees = []
    msp_counts = []
    for t in tree_sequence.trees():
        pi = [t.get_parent(j) for j in range(N + 1)]
        beta = [t.get_num_leaves(j) for j in range(N + 1)]
        msp_trees.append(pi)
        msp_counts.append(beta)
    assert msp_trees == local_trees
    assert msp_counts == local_counts


def run_verify(args):
    """
    Checks that the distibution of events we get is the same as msprime.
    """
    n = args.sample_size
    m = args.num_loci
    rho = args.recombination_rate
    msp_events = np.zeros(args.num_replicates)
    local_events = np.zeros(args.num_replicates)
    for j in range(args.num_replicates):
        random.seed(j)
        s = Simulator(n, m, rho, 10000)
        s.simulate()
        local_events[j] = s.num_re_events
        s = msprime.TreeSimulator(n)
        s.set_num_loci(m)
        s.set_scaled_recombination_rate(rho)
        s.set_random_seed(j)
        s.run()
        msp_events[j] = s.get_num_recombination_events()
    sm.graphics.qqplot(local_events)
    sm.qqplot_2samples(local_events, msp_events, line="45")
    pyplot.savefig(args.outfile, dpi=72)


def main():
    parser = argparse.ArgumentParser()
    # This is required to get uniform behaviour in Python2 and Python3
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.required = True

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify the local algorithm against msprime")
    verify_parser.add_argument("outfile")
    verify_parser.add_argument(
        "--sample-size", "-n", type=int, default=10)
    verify_parser.add_argument(
        "--num-loci", "-m", type=int, default=100)
    verify_parser.add_argument(
        "--num-replicates", "-R", type=int, default=1000)
    verify_parser.add_argument(
        "--recombination-rate", "-r", type=float, default=0.1)
    verify_parser.set_defaults(runner=run_verify)

    trees_parser = subparsers.add_parser(
        "trees",
        help="Shows the trees from an msprime history file")
    trees_parser.add_argument("history_file")

    trees_parser.set_defaults(runner=run_trees)

    args = parser.parse_args()
    args.runner(args)


if __name__ == "__main__":
    main()
