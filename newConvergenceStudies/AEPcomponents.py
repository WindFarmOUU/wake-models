from openmdao.api import Problem, Group, ExternalCode, IndepVarComp, Component
import numpy as np
import os
from getSamplePoints import getSamplePoints


class DakotaAEP(ExternalCode):
    """Use Dakota to estimate the AEP based on weighted power production."""

    def __init__(self, nDirections=10, dakotaFileName='dakotaAEP.in'):
        super(DakotaAEP, self).__init__()

        # set finite difference options (fd used for testing only)
        # self.fd_options['force_fd'] = True
        self.fd_options['form'] = 'central'
        self.fd_options['step_size'] = 1.0e-5
        self.fd_options['step_type'] = 'relative'

        # define inputs
        self.add_param('power', np.zeros(nDirections), units ='kW',
                       desc = 'vector containing the power production at each wind direction ccw from north')
        self.add_param('weights', np.zeros(nDirections),
                       desc = 'vector containing the weights for integration.')
        self.add_param('frequency', np.zeros(nDirections),
                       desc = 'vector containing the frequency from the probability density function.')

        # define output
        self.add_output('AEP', val=0.0, units='kWh', desc='total annual energy output of wind farm')

        # File in which the external code is implemented
        pythonfile = 'getDakotaAEP.py'
        self.options['command'] = ['python', pythonfile, dakotaFileName]

    def solve_nonlinear(self, params, unknowns, resids):

        # Generate the file with the power vector for Dakota
        power = params['power']
        rho = params['frequency']
        power = power*rho
        np.savetxt('powerInput.txt', power, header='power')

        # parent solve_nonlinear function actually runs the external code
        super(DakotaAEP, self).solve_nonlinear(params,unknowns,resids)

        os.remove('powerInput.txt')

        # Read in the calculated AEP
        # number of hours in a year
        hours = 8760.0
        unknowns['AEP'] = np.loadtxt('AEP.txt')*hours

        print 'In DakotaAEP'

    def linearize(self, params, unknowns, resids):

        J = linearize_function(params)
        return J


class SimpleAEP(Component):
    """Use simple integration to estimate the AEP based on weighted power production."""

    def __init__(self, nDirections=10):

        super(SimpleAEP, self).__init__()

        # set finite difference options (fd used for testing only)
        self.fd_options['form'] = 'central'
        self.fd_options['step_size'] = 1.0e-5
        self.fd_options['step_type'] = 'relative'

        # define inputs
        self.add_param('power', np.zeros(nDirections), units ='kW',
                       desc = 'vector containing the power production at each wind direction ccw from north')
        self.add_param('weights', np.zeros(nDirections),
                       desc = 'vector containing the weights for integration.')
        self.add_param('frequency', np.zeros(nDirections),
                       desc = 'vector containing the frequency from the probability density function.')

        # define output
        self.add_output('AEP', val=0.0, units='kWh', desc='total annual energy output of wind farm')

    def solve_nonlinear(self, params, unknowns, resids):

        power = params['power']
        rho = params['frequency']
        weight = params['weights'] # The weights of the integration points

        # number of hours in a year
        hours = 8760.0

        # calculate approximate AEP
        AEP = sum(power*weight*rho)*hours

        # promote AEP result to class attribute
        unknowns['AEP'] = AEP

        print 'In SimpleAEP'

    def linearize(self, params, unknowns, resids):

        J = linearize_function(params)
        return J


def linearize_function(params):

    power = params['power']
    weight = params['weights'] # The weights of the integration points
    rho = params['frequency']
    # number of hours in a year
    hours = 8760.0
    dAEP_dpower = weight*rho*hours
    dAEP_dweight = power*rho*hours
    dAEP_drho = power*weight*hours

    J = {}
    J[('AEP', 'power')] = np.array([dAEP_dpower])
    J[('AEP', 'weights')] = np.array([dAEP_dweight])
    J[('AEP', 'frequency')] = np.array([dAEP_drho])

    return J


if __name__ == "__main__":

    from WindFreqFunctions import wind_direction_pdf
    dakotaFileName = 'dakotaAEPdirection.in'
    winddirections, weights = getSamplePoints(dakotaFileName)
    f = wind_direction_pdf()
    rho = f(winddirections)
    prob = Problem(root=Group())
    prob.root.add('p', IndepVarComp('power', np.random.rand(10)))
    prob.root.add('w', IndepVarComp('weight', weights))
    prob.root.add('rho', IndepVarComp('frequency', rho))
    # prob.root.add('DakotaAEP', DakotaAEP(dakotaFileName=dakotaFileName))
    prob.root.add('DakotaAEP', SimpleAEP())
    prob.root.connect('p.power', 'DakotaAEP.power')
    prob.root.connect('w.weight', 'DakotaAEP.weights')
    prob.root.connect('rho.frequency', 'DakotaAEP.frequency')
    prob.setup()
    prob.run()
    print 'AEP = ', (prob.root.DakotaAEP.unknowns['AEP'])
    print 'power directions = ', (prob.root.DakotaAEP.params['power'])
    print prob.root.DakotaAEP.params.keys()
    # The DakotaAEP.power_directions key is not recognized
    # J = prob.calc_gradient(['DakotaAEP.AEP'], ['DakotaAEP.power'])
    # J = prob.calc_gradient(['DakotaAEP.AEP'], ['p.power'])
    # print 'power directions gradient = ', J

    # This check works
    data = prob.check_partial_derivatives()