# Copyright (C) 1996-2011 Power System Engineering Research Center
# Copyright (C) 2010-2011 Richard Lincoln
#
# PYPOWER is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# PYPOWER is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PYPOWER. If not, see <http://www.gnu.org/licenses/>.

import logging

from numpy import array, zeros, ones, Inf, copy, r_
from numpy import flatnonzero as find
from scipy.sparse import csr_matrix as sparse

logger = logging.getLogger(__name__)

class opf_model(object):
    """This class implements the OPF model object used to encapsulate
    a given OPF problem formulation. It allows for access to optimization
    variables, constraints and costs in named blocks, keeping track of the
    ordering and indexing of the blocks as variables, constraints and costs
    are added to the problem.

    @see: U{http://www.pserc.cornell.edu/matpower/}
    """

    def __init__(self, ppc):
        #: PYPOWER case dict used to build the object.
        self.ppc = ppc

        self.var = {}
        self.nln = {}
        self.lin = {}
        self.cost = {}
        self.userdata = {}


    def add_constraints(self, name, AorN, l, u=None, varsets=None):
        """Adds a set of constraints to the model.

        Linear constraints are of the form L <= A * x <= U, where
        x is a vector made of of the vars specified in VARSETS (in
        the order given). This allows the A matrix to be defined only
        in terms of the relevant variables without the need to manually
        create a lot of zero columns. If VARSETS is empty, x is taken
        to be the full vector of all optimization variables. If L or
        U are empty, they are assumed to be appropriately sized vectors
        of -Inf and Inf, respectively.

        For nonlinear constraints, the 3rd argument, N, is the number
        of constraints in the set. Currently, this is used internally
        by PYPOWER, but there is no way for the user to specify
        additional nonlinear constraints.
        """
        if u is None:
        ## nonlinear
            ## prevent duplicate named constraint sets
            if name in self.nln["idx"]["N"]:
                logger.error("opf_model.add_constraints: nonlinear constraint set named '%s' already exists" % name)

            ## add info about this nonlinear constraint set
            self.nln["idx"]["i1"][name] = self.nln["N"] + 1    ## starting index
            self.nln["idx"]["iN"][name] = self.nln["N"] + AorN ## ing index
            self.nln["idx"]["N"][name]  = AorN            ## number of constraints

            ## update number of nonlinear constraints and constraint sets
            self.nln["N"]  = self.nln["idx"]["iN"][name]
            self.nln["NS"] = self.nln["NS"] + 1

            ## put name in ordered list of constraint sets
            self.nln["order"][self.nln["NS"]] = name
        else:                ## linear
            ## prevent duplicate named constraint sets
            if name in self.lin["idx"]["N"]:
                logger.error('opf_model.add_constraints: linear constraint set named ''%s'' already exists' % name)

            if varsets is None:
                varsets = []

            N, M = AorN.shape
            if len(l) == 0:                   ## default l is -Inf
                l = -Inf * ones(N)

            if len(u) == 0:                   ## default u is Inf
                u = Inf * ones(N)

            if len(varsets) == 0:
                varsets = self.var["order"]

            ## check sizes
            if l.shape[0] != N or u.shape[0] != N:
                logger.error('opf_model.add_constraints: sizes of A, l and u must match')

            nv = 0
            for k in range(len(varsets)):
                nv = nv + self.var["idx"]["N"][varsets[k]]

            if M != nv:
                logger.error('opf_model.add_constraints: number of columns of A does not match\nnumber of variables, A is %d x %d, nv = %d\n' % (N, M, nv))

            ## add info about this linear constraint set
            self.lin["idx"]["i1"][name]  = self["lin"]["N"] + 1   ## starting index
            self.lin["idx"]["iN"][name]  = self["lin"]["N"] + N   ## ing index
            self.lin["idx"]["N"][name]   = N              ## number of constraints
            self.lin["data"]["A"][name]  = AorN
            self.lin["data"]["l"][name]  = l
            self.lin["data"]["u"][name]  = u
            self.lin["data"]["vs"][name] = varsets

            ## update number of vars and var sets
            self.lin["N"]  = self.lin["idx"]["iN"][name]
            self.lin["NS"] = self.lin["NS"] + 1

            ## put name in ordered list of var sets
            self.lin["order"][self.lin["NS"]] = name


    def add_costs(self, name, cp, varsets):
        """Adds a set of user costs to the model.

        Adds a named block of user-defined costs to the model. Each set is
        defined by the CP struct described below. All user-defined sets of
        costs are combined together into a single set of cost parameters in
        a single CP struct by BULD_COST_PARAMS. This full aggregate set of
        cost parameters can be retreived from the model by GET_COST_PARAMS.

        Let x refer to the vector formed by combining the specified VARSETS,
        and f_u(x, CP) be the cost at x corresponding to the cost parameters
        contained in CP, where CP is a struct with the following fields:
            N      - nw x nx sparse matrix
            Cw     - nw x 1 vector
            H      - nw x nw sparse matrix (optional, all zeros by default)
            dd, mm - nw x 1 vectors (optional, all ones by default)
            rh, kk - nw x 1 vectors (optional, all zeros by default)

        These parameters are used as follows to compute f_u(x, CP)

            R  = N*x - rh

                    /  kk(i),  R(i) < -kk(i)
            K(i) = <   0,     -kk(i) <= R(i) <= kk(i)
                    \ -kk(i),  R(i) > kk(i)

            RR = R + K

            U(i) =  /  0, -kk(i) <= R(i) <= kk(i)
                    \  1, otherwise

            DDL(i) = /  1, dd(i) = 1
                     \  0, otherwise

            DDQ(i) = /  1, dd(i) = 2
                     \  0, otherwise

            Dl = diag(mm) * diag(U) * diag(DDL)
            Dq = diag(mm) * diag(U) * diag(DDQ)

            w = (Dl + Dq * diag(RR)) * RR

            f_u(x, CP) = 1/2 * w'*H*w + Cw'*w
        """
        ## prevent duplicate named cost sets
        if name in self.cost["idx"]["N"]:
            logger.error('opf_model.add_costs: cost set named ''%s'' already exists' % name)

        if varsets is None:
            varsets = []

        if len(varsets) == 0:
            varsets = self.var["order"]

        nw, nx = cp["N"].shape

        ## check sizes
        nv = 0
        for k in range(len(varsets)):
            nv = nv + self.var["idx"]["N"][varsets[k]]

        if nx != nv:
            if nw == 0:
                cp["N"] = sparse(nw, nx)
            else:
                logger.error('opf_model.add_costs: number of columns in N (%d x %d) does not match\nnumber of variables (%d)\n' % (nw, nx, nv))

        if cp["Cw"].shape[0] != nw:
            logger.error('opf_model.add_costs: number of rows of Cw (%d x %d) and N (%d x %d) must match\n' % (cp["Cw"].shape[0], nw, nx))

        if 'H' in cp & (cp["H"].shape[0] != nw | cp["H"].shape[1] != nw):
            logger.error('opf_model.add_costs: both dimensions of H (%d x %d) must match the number of rows in N (%d x %d)\n' % (cp["H"].shape, nw, nx))

        if 'dd' in cp & cp["dd"].shape[0] != nw:
            logger.error('opf_model.add_costs: number of rows of dd (%d x %d) and N (%d x %d) must match\n' % (cp["dd"].shape, nw, nx))

        if 'rh' in cp & cp["rh"].shape[0] != nw:
            logger.error('opf_model.add_costs: number of rows of rh (%d x %d) and N (%d x %d) must match\n' % (cp["rh"].shape, nw, nx))

        if 'kk' in cp & cp["kk"].shape[0] != nw:
            logger.error('opf_model.add_costs: number of rows of kk (%d x %d) and N (%d x %d) must match\n' % (cp["kk"].shape, nw, nx))

        if 'mm' in cp & cp["mm"].shape[0] != nw:
            logger.error('opf_model.add_costs: number of rows of mm (%d x %d) and N (%d x %d) must match\n' % (cp["mm"].shape, nw, nx))

        ## add info about this user cost set
        self.cost["idx"]["i1"][name]  = self.cost["N"] + 1     ## starting index
        self.cost["idx"]["iN"][name]  = self.cost["N"] + nw    ## ing index
        self.cost["idx"]["N"][name]   = nw                ## number of costs (nw)
        self.cost["data"]["N"][name]  = cp["N"]
        self.cost["data"]["Cw"][name] = cp["Cw"]
        self.cost["data"]["vs"][name] = varsets
        if 'H' in cp:
            self.cost["data"]["H"][name]  = cp["H"]

        if 'dd' in cp:
            self.cost["data"]["dd"]["name"] = cp["dd"]

        if 'rh' in cp:
            self.cost["data"]["rh"]["name"] = cp["rh"]

        if 'kk' in cp:
            self.cost["data"]["kk"]["name"] = cp["kk"]

        if 'mm' in cp:
            self.cost["data"]["mm"]["name"] = cp["mm"]

        ## update number of vars and var sets
        self.cost["N"]  = self.cost["idx"]["iN"]["name"]
        self.cost["NS"] = self.cost["NS"] + 1

        ## put name in ordered list of var sets
        self.cost["order"][self.cost["NS"]] = name


    def add_vars(self, name, N, v0=None, vl=None, vu=None):
        """ Adds a set of variables to the model.

        Adds a set of variables to the model, where N is the number of
        variables in the set, V0 is the initial value of those variables,
        and VL and VU are the lower and upper bounds on the variables.
        The defaults for the last three arguments, which are optional,
        are for all values to be initialized to zero (V0 = 0) and unbounded
        (VL = -Inf, VU = Inf).
        """
        ## prevent duplicate named var sets
        if name in self.var["idx"]["N"]:
            logger.error('opf_model.add_vars: variable set named ''%s'' already exists' % name)

        if v0 is None or len(v0) == 0:
            v0 = zeros(N)           ## init to zero by default

        if vl is None or len(vl) == 0:
            vl = -Inf * ones(N)     ## unbounded below by default

        if vu is None or len(vu) == 0:
            vu = Inf * ones(N)      ## unbounded above by default


        ## add info about this var set
        self.var["idx"]["i1"][name]  = self.var["N"] + 1   ## starting index
        self.var["idx"]["iN"][name]  = self.var["N"] + N   ## ing index
        self.var["idx"]["N"][name]   = N              ## number of vars
        self.var["data"]["v0"][name] = v0             ## initial value
        self.var["data"]["vl"][name] = vl             ## lower bound
        self.var["data"]["vu"][name] = vu             ## upper bound

        ## update number of vars and var sets
        self.var["N"]  = self.var["idx"]["iN"][name]
        self.var["NS"] = self.var["NS"] + 1

        ## put name in ordered list of var sets
        self.var["order"][self.var["NS"]] = name


    def build_cost_params(self):
        """Builds and saves the full generalized cost parameters.

        Builds the full set of cost parameters from the individual named
        sub-sets added via ADD_COST. Skips the building process if it has
        already been done, unless a second input argument is present.

        These cost parameters can be retrieved by calling GET_COST_PARAMS
        and the user-defined costs evaluated by calling COMPUTE_COST.
        """
        ## initialize parameters
        nw = self.cost["N"]
#        nnzN = 0
#        nnzH = 0
#        for k in range(self.cost["NS"]):
#            name = self.cost["order"][k]
#            nnzN = nnzN + nnz(self.cost["data"]["N"][name])
#            if name in self.cost["data"]["H"]:
#                nnzH = nnzH + nnz(self.cost["data"]["H"][name])

        N = sparse((nw, self.var["N"]))
        Cw = zeros(nw)
        H = sparse((nw, nw))                ## default => no quadratic term
        dd = ones(nw)                       ## default => linear
        rh = copy(Cw)                          ## default => no shift
        kk = copy(Cw)                          ## default => no dead zone
        mm = copy(dd)                          ## default => no scaling

        ## fill in each piece
        for k in range(self.cost["NS"]):
            name = self.cost["order"][k]
            Nk = self.cost["data"]["N"][name]          ## N for kth cost set
            i1 = self.cost["idx"]["i1"][name]          ## starting row index
            iN = self.cost["idx"]["iN"][name]          ## ing row index
            if self.cost["idx"]["N"][name]:            ## non-zero number of rows to add
                vsl = self.cost["data"]["vs"][name]    ## var set list
                kN = 0                                 ## initialize last col of Nk used
                for v in vsl:
                    j1 = self.var["idx"]["i1"][v]    ## starting column in N
                    jN = self.var["idx"]["iN"][v]    ## ing column in N
                    k1 = kN + 1                      ## starting column in Nk
                    kN = kN + self.var["idx"]["N"][v]## ing column in Nk
                    N[i1:iN, j1:jN] = Nk[:, k1:kN]

                Cw[i1:iN] = self.cost["data"]["Cw"][name]
                if name in self.cost["data"]["H"]:
                    H[i1:iN, i1:iN] = self.cost["data"]["H"][name]

                if name in self.cost["data"]["dd"]:
                    dd[i1:iN] = self.cost["data"]["dd"][name]

                if name in self.cost["data"]["rh"]:
                    rh[i1:iN] = self.cost["data"]["rh"][name]

                if name in self.cost["data"]["kk"]:
                    kk[i1:iN] = self.cost["data"]["kk"][name]

                if name in self.cost["data"]["mm"]:
                    mm[i1:iN] = self.cost["data"]["mm"][name]

        ## save in object
        self.cost["params"] = {
            'N': N, 'Cw': Cw, 'H': H, 'dd': dd, 'rh': rh, 'kk': kk, 'mm': mm }


    def compute_cost(self, x, name=None):
        """ Computes a user-defined cost.

        Computes the value of a user defined cost, either for all user
        defined costs or for a named set of costs. Requires calling
        BUILD_COST_PARAMS first to build the full set of parameters.

        Let X be the full set of optimization variables and F_U(X, CP) be the
        user-defined cost at X, corresponding to the set of cost parameters in
        the CP struct returned by GET_COST_PARAMS, where CP is a struct with the
        following fields:
            N      - nw x nx sparse matrix
            Cw     - nw x 1 vector
            H      - nw x nw sparse matrix (optional, all zeros by default)
            dd, mm - nw x 1 vectors (optional, all ones by default)
            rh, kk - nw x 1 vectors (optional, all zeros by default)

        These parameters are used as follows to compute F_U(X, CP)

            R  = N*x - rh

                    /  kk(i),  R(i) < -kk(i)
            K(i) = <   0,     -kk(i) <= R(i) <= kk(i)
                    \ -kk(i),  R(i) > kk(i)

            RR = R + K

            U(i) =  /  0, -kk(i) <= R(i) <= kk(i)
                    \  1, otherwise

            DDL(i) = /  1, dd(i) = 1
                     \  0, otherwise

            DDQ(i) = /  1, dd(i) = 2
                     \  0, otherwise

            Dl = diag(mm) * diag(U) * diag(DDL)
            Dq = diag(mm) * diag(U) * diag(DDQ)

            w = (Dl + Dq * diag(RR)) * RR

            F_U(X, CP) = 1/2 * w'*H*w + Cw'*w
        """
        if name is None:
            cp = self.get_cost_params()
        else:
            cp = self.get_cost_params(name)

        N, Cw, H, dd, rh, kk, mm = cp["N"], cp["Cw"], cp["H"], cp["dd"], cp["rh"], cp["kk"], cp["mm"]
        nw = N.shape[0]
        r = N * x - rh                 ## Nx - rhat
        iLT = find(r < -kk)            ## below dead zone
        iEQ = find(r == 0 & kk == 0)   ## dead zone doesn't exist
        iGT = find(r > kk)             ## above dead zone
        iND = r_[iLT, iEQ, iGT]        ## rows that are Not in the Dead region
        iL = find(dd == 1)             ## rows using linear function
        iQ = find(dd == 2)             ## rows using quadratic function
        LL = sparse((1, (iL, iL)), (nw, nw))
        QQ = sparse((1, (iQ, iQ)), (nw, nw))
        kbar = sparse((r_[   ones(len(iLT), 1),
                             zeros(len(iEQ), 1),
                             -ones(len(iGT), 1)], (iND, iND)), (nw, nw)) * kk
        rr = r + kbar                  ## apply non-dead zone shift
        M = sparse((mm(iND), (iND, iND)), (nw, nw))  ## dead zone or scale
        diagrr = sparse((rr, (range(nw), range(nw))), (nw, nw))

        ## linear rows multiplied by rr(i), quadratic rows by rr(i)^2
        w = M * (LL + QQ * diagrr) * rr

        f = (w.T * H * w) / 2 + Cw.T * w

        return f


    def display(self):
        """Displays the object.

        Displays the details of the variables, constraints, costs included in
        the model.
        """
        if self.var["NS"]:
            print '\n%-22s %5s %8s %8s %8s\n' % ('VARIABLES', 'name', 'i1', 'iN', 'N')
            print '%-22s %5s %8s %8s %8s\n' % ('=========', '------', '-----', '-----', '------')
            for k in range(self.var["NS"]):
                name = self.var["order"][k]
                idx = self.var["idx"]
                print '%15d:%12s %8d %8d %8d\n' % (k, name, idx["i1"][name], idx["iN"][name], idx["N"][name])

            print '%15s%31s\n' % ('var["NS"] = %d' % self.var["NS"], 'var["N"] = %d' % self.var["N"])
            print '\n'
        else:
            print '%s  :  <none>\n' % 'VARIABLES'

        if self.nln["NS"]:
            print '\n%-22s %5s %8s %8s %8s\n' % ('nonlinear CONSTRAINTS', 'name', 'i1', 'iN', 'N')
            print '%-22s %5s %8s %8s %8s\n' % ('======================', '------', '-----', '-----', '------')
            for k in range(self.nln["NS"]):
                name = self.nln["order"][k]
                idx = self.nln["idx"]
                print '%15d:%12s %8d %8d %8d\n' % (k, name, idx["i1"][name], idx["iN"][name], idx["N"][name])

            print '%15s%31s\n' % ('nln["NS"] = %d' % self.nln["NS"], 'nln["N"] = %d' % self.nln["N"])
            print '\n'
        else:
            print '%s  :  <none>\n' % 'nonlinear CONSTRAINTS'

        if self.lin["NS"]:
            print '\n%-22s %5s %8s %8s %8s\n' % ('LINEAR CONSTRAINTS', 'name', 'i1', 'iN', 'N')
            print '%-22s %5s %8s %8s %8s\n' % ('==================', '------', '-----', '-----', '------')
            for k in range(self.lin["NS"]):
                name = self.lin["order"][k]
                idx = self.lin["idx"]
                print '%15d:%12s %8d %8d %8d\n' % (k, name, idx["i1"][name], idx["iN"][name], idx["N"][name])

            print '%15s%31s\n' % ('lin["NS"] = %d' % self.lin["NS"], 'lin["N"] = %d' % self.lin["N"])
            print '\n'
        else:
            print '%s  :  <none>\n' % 'LINEAR CONSTRAINTS'

        if self.cost["NS"]:
            print '\n%-22s %5s %8s %8s %8s\n' % ('COSTS', 'name', 'i1', 'iN', 'N')
            print '%-22s %5s %8s %8s %8s\n' % ('=====', '------', '-----', '-----', '------')
            for k in range(self.cost["NS"]):
                name = self.cost["order"][k]
                idx = self.cost["idx"]
                print '%15d:%12s %8d %8d %8d\n' % (k, name, idx["i1"][name], idx["iN"][name], idx["N"][name])

            print '%15s%31s\n' % ('cost["NS"] = %d' % self.cost["NS"], 'cost["N"] = %d' % self.cost["N"])
            print '\n'
        else:
            print '%s  :  <none>\n' % 'COSTS'

        print '  mpc = '
        if len(self.ppc) > 0:
            print '\n'

        print self.ppc

        print '  userdata = '
        if len(self.userdata) > 0:
            print '\n'

        print self.userdata


    def get_cost_params(self, name=None):
        """Returns the cost parameter struct for user-defined costs.

        Requires calling BUILD_COST_PARAMS first to build the full set of
        parameters. Returns the full cost parameter struct for all user-defined
        costs that incorporates all of the named cost sets added via ADD_COSTS,
        or, if a name is provided it returns the cost struct corresponding to
        the named set of cost rows (N still has full number of columns).

        The cost parameters are returned in a dict with the following fields:
            N      - nw x nx sparse matrix
            Cw     - nw x 1 vector
            H      - nw x nw sparse matrix (optional, all zeros by default)
            dd, mm - nw x 1 vectors (optional, all ones by default)
            rh, kk - nw x 1 vectors (optional, all zeros by default)
        """
        if not 'params' in self.cost:
            logger.error('opf_model.get_cost_params: must call build_cost_params first')

        cp = self.cost["params"]

        if name is not None:
            if self.getN('cost', name):
                idx = range(self.cost["idx"]["i1"][name], self.cost["idx"]["iN"][name])
                cp["N"]  = cp["N"][idx, :]
                cp["Cw"] = cp["Cw"][idx]
                cp["H"]  = cp["H"][idx, :]
                cp["dd"] = cp["dd"][idx]
                cp["rh"] = cp["rh"][idx]
                cp["kk"] = cp["kk"][idx]
                cp["mm"] = cp["mm"][idx]

        return cp


    def get_idx(self):
        """ Returns the idx struct for vars, lin/nln constraints, costs.

        Returns a structure for each with the beginning and ing
        index value and the number of elements for each named block.
        The 'i1' field (that's a one) is a struct with all of the
        starting indices, 'iN' contains all the ing indices and
        'N' contains all the sizes. Each is a struct whose fields are
        the named blocks.

        Examples:
            [vv, ll, nn] = get_idx(om)

            For a variable block named 'z' we have ...
                vv.i1.z - starting index for 'z' in optimization vector x
                vv.iN.z - ing index for 'z' in optimization vector x
                vv["N"]    - number of elements in 'z'

            To extract a 'z' variable from x:
                z = x(vv.i1.z:vv.iN.z)

            To extract the multipliers on a linear constraint set
            named 'foo', where mu_l and mu_u are the full set of
            linear constraint multipliers:
                mu_l_foo = mu_l(ll.i1.foo:ll.iN.foo)
                mu_u_foo = mu_u(ll.i1.foo:ll.iN.foo)

            The number of nonlinear constraints in a set named 'bar':
                nbar = nn["N"].bar
              (note: the following is preferable ...
                nbar = getN(om, 'nln', 'bar')
              ... if you haven't already called get_idx to get nn.)
        """
        vv = self.var["idx"]
        ll = self.lin["idx"]
        nn = self.nln["idx"]
        cc = self.cost["idx"]

        return vv, ll, nn, cc


    def get_ppc(self):
        """Returns the PYPOWER case dict.
        """
        return self.ppc


    def getN(self, selector, name=None):
        """Returns the number of variables, constraints or cost rows.

        Returns either the total number of variables/constraints/cost rows
        or the number corresponding to a specified named block.

        Examples:
            N = getN(om, 'var')         : total number of variables
            N = getN(om, 'lin')         : total number of linear constraints
            N = getN(om, 'nln')         : total number of nonlinear constraints
            N = getN(om, 'cost')        : total number of cost rows (in N)
            N = getN(om, 'var', name)   : number of variables in named set
            N = getN(om, 'lin', name)   : number of linear constraints in named set
            N = getN(om, 'nln', name)   : number of nonlinear cons. in named set
            N = getN(om, 'cost', name)  : number of cost rows (in N) in named set
        """
        if name is not None:
            N = getattr(self, selector)["N"]
        else:
            if name in getattr(self, selector)["idx"]["N"]:
                N = getattr(self, selector)["idx"]["N"][name]
            else:
                N = 0
        return N


    def getv(self, name=None):
        """Returns initial value, lower bound and upper bound for opt variables.

        Returns the Returns value, lower bound and upper bound for the full
        optimization variable vector, or for a specific named variable set.

        Examples:
            x, xmin, xmax = getv(om)
            Pg, Pmin, Pmax = getv(om, 'Pg')
        """
        if name is None:
            v0 = array([]); vl = array([]); vu = array([])
            for k in range(self.var["NS"]):
                name = self.var["order"][k]
                v0 = r_[ v0, self.var["data"]["v0"][name] ]
                vl = r_[ vl, self.var["data"]["vl"][name] ]
                vu = r_[ vu, self.var["data"]["vu"][name] ]
        else:
            if name in self.var["idx"]["N"]:
                v0 = self.var["data"]["v0"][name]
                vl = self.var["data"]["vl"][name]
                vu = self.var["data"]["vu"][name]
            else:
                v0 = array([])
                vl = array([])
                vu = array([])


    def linear_constraints(self):
        """Builds and returns the full set of linear constraints.

        Builds the full set of linear constraints based on those added by
        ADD_CONSTRAINTS.

            L <= A * x <= U
        """

        ## initialize A, l and u
#        nnzA = 0
#        for k in range(self.lin["NS"]):
#            nnzA = nnzA + nnz(self.lin["data"].A.(self.lin.order{k}))

        A = sparse((self.lin["N"], self.var["N"]))
        u = Inf * ones(self.lin["N"])
        l = -u

        ## fill in each piece
        for k in range(self.lin["NS"]):
            name = self.lin["order"][k]
            N = self.lin["idx"]["N"][name]
            if N:                                ## non-zero number of rows to add
                Ak = self.lin["data"]["A"][name]          ## A for kth linear constrain set
                i1 = self.lin["idx"]["i1"][name]          ## starting row index
                iN = self.lin["idx"]["iN"][name]          ## ing row index
                vsl = self.lin["data"]["vs"][name]        ## var set list
                kN = 0                             ## initialize last col of Ak used
                Ai = sparse((N, self.var["N"]))
                for v in vsl:
                    j1 = self.var["idx"]["i1"][v]    ## starting column in A
                    jN = self.var["idx"]["iN"][v]    ## ing column in A
                    k1 = kN + 1                      ## starting column in Ak
                    kN = kN + self.var["idx"]["N"][v]## ing column in Ak
                    Ai[:, j1:jN] = Ak[:, k1:kN]

                A[i1:iN, :] = Ai
                l[i1:iN] = self.lin["data"]["l"][name]
                u[i1:iN] = self.lin["data"]["u"][name]

        return A, l, u


    def userdata(self, name, val=None):
        """Used to save or retrieve values of user data.

        This function allows the user to save any arbitrary data in the object
        for later use. This can be useful when using a user function to add
        variables, constraints, costs, etc. For example, suppose some special
        indexing is constructed when adding some variables or constraints.
        This indexing data can be stored and used later to "unpack" the results
        of the solved case.
        """
        if val is not None:
            self.userdata[name] = val
        else:
            if name in self.userdata:
                return self.userdata[name]
            else:
                return None