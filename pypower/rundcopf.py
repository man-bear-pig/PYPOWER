# Copyright (C) 1996-2011 Power System Engineering Research Center
# Copyright (C) 2009-2011 Richard Lincoln
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

from ppoption import ppoption
from runopf import runopf

def rundcopf(casedata='case9', ppopt=None, fname='', solvedcase=''):
    """ Runs a DC optimal power flow.

    @see: L{runopf}, L{runduopf}
    @see: U{http://www.pserc.cornell.edu/matpower/}
    """
    ## default arguments
    ppopt = ppoption() if ppopt is None else ppopt

    ppopt = ppoption(ppopt, PF_DC=True)
    return runopf(casedata, ppopt, fname, solvedcase)